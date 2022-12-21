from .utils import *
from shazamio import Shazam
from scipy.signal import argrelextrema, savgol_filter
from scipy.ndimage import uniform_filter1d
from pydub.silence import split_on_silence, detect_silence
from pydub.utils import mediainfo
from numpy import inf
import asyncio
import os.path
import time


def split(audio: AudioSegment, track_count: int):

    # rough split of the audio
    chunks = split_on_silence(audio, min_silence_len=1000, silence_thresh=-16, seek_step=100)
    t0 = time.time()

    silence_thresh = -256
    lowest_silence_thresh = 0
    delta_st = silence_thresh/2
    silent_count = track_count
    count = 0

    while delta_st < -1 or count != silent_count:
        print("Current silence threshold: {}".format(silence_thresh))
        silent_sections = detect_silence(audio, min_silence_len=500, silence_thresh=silence_thresh, seek_step=100)
        count = len(silent_sections)
        print("Current section count: {}\n".format(count))

        if count == silent_count:
            if silence_thresh < lowest_silence_thresh:
                lowest_silence_thresh = silence_thresh
            silence_thresh += delta_st
        else:
            silence_thresh -= delta_st

        delta_st /= 2


    t1 = time.time() - t0

    chunks.sort(key=lambda ch: ch.dBFS)
    dBFS_floor = chunks[track_count].dBFS
    # fine split
    chunks = split_on_silence(audio, min_silence_len=1000, silence_thresh=dBFS_floor, seek_step=100)
    if len(chunks) != track_count:
        print('hm...')
    return chunks


def parse_md(track_info) -> dict:
    md = {'artist': track_info['subtitle'] if 'subtitle' in track_info else 'Implement better artist search...'}
    if 'sections' in track_info:
        for s in track_info['sections']:
            if 'metadata' in s:
                for m in s['metadata']:
                    if 'title' in m and 'text' in m:
                        md[m['title'].lower()] = m['text']
    return md

def get_minima_indices_guess(length_of_tracks_deci_secs, total_duration_secs):
    minima_indices_guess = [0.0]
    for t in length_of_tracks_deci_secs:
        minima_indices_guess.append(minima_indices_guess[-1] + t)
    minima_indices_guess.append(10*total_duration_secs)
    end_delta = minima_indices_guess[-1] - minima_indices_guess[-2]
    del minima_indices_guess[-2]

    # if the sum exceeds the total duration by more than 1 second -> break
    if end_delta < -100: 
        print("Sum of the length of the tracks in db exceeds duration of provided audio.")
        return []

    dt = end_delta / (len(length_of_tracks_deci_secs) + 1)
    for i in range(1, len(minima_indices_guess)-1):
        minima_indices_guess[i] += (i+1)*dt
    return np.array(minima_indices_guess)

def get_minima_indices_detection(length_of_tracks_deci_secs, track_count, audio):
    dbfs_data = np.array([audio[i:i+100].dBFS for i in range(0, int(audio.duration_seconds*1e3), 100)])
    dbfs_data[dbfs_data == -inf] = np.min(dbfs_data[dbfs_data != -inf])
    minima_indices = [0, int(10*audio.duration_seconds)]
    length_of_tracks_deci_secs.sort()
    # leave at least 3/4th of the shortest track between the minima
    min_time_between_parts = .75*length_of_tracks_deci_secs[0]
    
    # TODO double check minima_indices with track length from tracks_info
    for idx in np.argsort(dbfs_data):
        minima_count = len(minima_indices)
        
        if minima_count == track_count + 1: # beginning, parts between the tracks and the end
            break
        
        if  minima_count == 0 or all([((minima_idx - idx)**2)**.5 > min_time_between_parts for minima_idx in minima_indices]):
            minima_indices.append(idx)
            print("Identified timestamp at minute {}".format(0.1*idx/60))

    minima_indices.sort()
    return np.array(minima_indices) * 100
async def main(user_input: str):
    if user_input.startswith('http') or user_input.startswith('www'):
        print('Scraping audio from {}'.format(user_input))
        audio = from_yt(user_input)
    elif os.path.isfile(user_input):
        print('Loading audio file {}'.format(user_input))
        audio = from_file(user_input)
    else:
        await main(input("Unable to parse {}\nTry again: "))
        return

    shazam = Shazam()
    print('Identifying audio...')
    audio_info = await shazam.recognize_song(audio)

    if len(audio_info['matches']) == 0:
        print('Unable to recognize the audio...')
        return

    album_info = audio_info['track']

    album_md = parse_md(album_info)
    print('Identified:')
    [print(f'\t{k}: {v}') for k, v in album_md.items()]

    print('Getting album information...')
    album_info = get_album_info(album_info['albumadamid'])
    tracks_info = {}
    if len(album_info) == 0:
        tracks_info['track_count'] = input("No album information found. Provide track count: ")
    else:
        tracks_info['track_count'] = album_info['attributes']['trackCount']
        tracks_info['tracks'] = [t['attributes'] for t in album_info['relationships']['tracks']['data']]

    print("Identifying the timestamps of the tracks...")

    length_of_tracks = [t['durationInMillis']/100.0 for t in tracks_info['tracks']]
    
    minima_indices = get_minima_indices_guess(length_of_tracks, audio.duration_seconds)
    if len(minima_indices) == 0:
        print("Trying to detect splits by identifying silent parts...")
        minima_indices = get_minima_indices_detection(length_of_tracks, tracks_info['track_count'], audio)

    print("Identified timestamps [minutes]:\n{}".format(minima_indices/600))

    minima_indices *= 100

    print('Splitting album into {} tracks...'.format(tracks_info['track_count']))
    export_dir = '{}/../export/{} - {}'.format(os.path.dirname(os.path.abspath(__file__)), album_md['artist'], album_md['album'])
    os.makedirs(export_dir, exist_ok=True)
    for i in range(len(minima_indices) - 1):
        metadata = {
            "artist": album_md['artist'],
            "title": tracks_info['tracks'][i]['name'],
            "album": album_md['album'],
            "genre": ', '.join(tracks_info['tracks'][i]['genreNames']),
            "track": i+1,
            "released": tracks_info['tracks'][i]['releaseDate']
        }
        print("Exporting track #{}:\n\t{}\n".format(i+1, metadata))
        audio[minima_indices[i]:minima_indices[i+1]].export(export_dir + '/{} - {}.mp3'.format(metadata['artist'], metadata['title']), tags=metadata)

    print("Done")
    return


def app():
    user_input = input("Enter the YouTube URL or Audio File Path: ")
    # user_input = 'https://www.youtube.com/watch?v=2jhmxHLJ1XU'
    # user_input = 'D:\Downloads\Elder - Innate Passage\Elder - Innate Passage (128kbit_AAC).m4a'
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main(user_input))

if __name__ == '__main__':
    app()