import pydub.exceptions
import numpy as np
from pytube import YouTube
from io import BytesIO
from pydub import AudioSegment
from pydub.silence import split_on_silence, detect_silence
from numpy import inf
import urllib.request
import json


def from_yt(yt_link: str) -> AudioSegment:
    buffer = BytesIO()
    yt = YouTube(yt_link)
    file = yt.streams.filter(only_audio=True).order_by('bitrate').desc().first()
    print("Found highest bitrate of {}kbps as {} format. Downloading...".format(1e-3*file.bitrate, file.audio_codec))
    file.stream_to_buffer(buffer)
    buffer.seek(0)
    try:
        return AudioSegment.from_file(buffer, format=file.audio_codec)
    except pydub.exceptions.CouldntDecodeError:
        try:
            buffer.seek(0)
            return AudioSegment.from_file(buffer, format=file.subtype)
        except pydub.exceptions.CouldntDecodeError:
            raise pydub.exceptions.CouldntDecodeError()


def from_file(path: str) -> AudioSegment:
    return AudioSegment.from_file(path, format=path[-3:].lower())


def get_album_info(album_id: str, language='gb') -> dict:
    try:
        data = urllib.request.urlopen(f'https://www.shazam.com/services/amapi/v1/catalog/{language}/albums/' + album_id)
        data = json.load(data)
        if 'data' in data:
            data = data['data']
            if len(data) == 1:
                data = data[0]
            return data
        return {}
    except:
        return {}

def parse_md(track_info) -> dict:
    md = {'artist': track_info['subtitle'] if 'subtitle' in track_info else 'Implement better artist search...'}
    if 'sections' in track_info:
        for s in track_info['sections']:
            if 'metadata' in s:
                for m in s['metadata']:
                    if 'title' in m and 'text' in m:
                        md[m['title'].lower()] = m['text']
    return md

def get_minima_indices_metadata(length_of_tracks_deci_secs, total_duration_secs):
    """
    return split points from metadata inforation"""
    minima_indices_guess = [0.0]
    for t in length_of_tracks_deci_secs:
        minima_indices_guess.append(minima_indices_guess[-1] + t)
    minima_indices_guess.append(10*total_duration_secs)
    end_delta = minima_indices_guess[-1] - minima_indices_guess[-2]
    del minima_indices_guess[-2]

    # if the sum exceeds the total duration by more than 10 second -> break
    if end_delta < -1000: 
        print("Sum of the length of the tracks in db exceeds duration of provided audio.")
        return []

    # spread any end_delta over the whole album 
    # TODO use get_minima_indices_detection methods when end_delta is too big
    dt = end_delta / (len(length_of_tracks_deci_secs) + 1)
    for i in range(1, len(minima_indices_guess)-1):
        minima_indices_guess[i] += (i+1)*dt
    return np.array(minima_indices_guess)

def get_minima_indices_detection(length_of_tracks_deci_secs, track_count, audio):
    """
    if the length of the tracks is unknows or faulty, try finding the splits by identifying the minima in the dbfs data"""
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

def split(audio: AudioSegment, track_count: int):
    """
    dev
    """

    # rough split of the audio
    chunks = split_on_silence(audio, min_silence_len=1000, silence_thresh=-16, seek_step=100)

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


    chunks.sort(key=lambda ch: ch.dBFS)
    dBFS_floor = chunks[track_count].dBFS
    # fine split
    chunks = split_on_silence(audio, min_silence_len=1000, silence_thresh=dBFS_floor, seek_step=100)
    if len(chunks) != track_count:
        print('hm...')
    return chunks