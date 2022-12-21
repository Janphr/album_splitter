from .utils import *
from shazamio import Shazam
from scipy.signal import argrelextrema, savgol_filter
from scipy.ndimage import uniform_filter1d
from pydub.utils import mediainfo
import asyncio
import os.path


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
    
    minima_indices = get_minima_indices_metadata(length_of_tracks, audio.duration_seconds)
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
            "title": tracks_info['tracks'][i]['name'].replace('/', '--'),
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
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main(user_input))

if __name__ == '__main__':
    app()