import pydub.exceptions
import numpy as np
from pytube import YouTube
from io import BytesIO
from pydub import AudioSegment
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


def to_file(path: str, buffer: BytesIO):
    pass


def get_album_info(album_id: str) -> dict:
    try:
        data = urllib.request.urlopen('https://www.shazam.com/services/amapi/v1/catalog/gb/albums/' + album_id)
        data = json.load(data)
        if 'data' in data:
            data = data['data']
            if len(data) == 1:
                data = data[0]
            return data
        return {}
    except:
        return {}

