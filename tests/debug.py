import asyncio
from album_splitter import split

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    loop.run_until_complete(split(input("Enter the YouTube URL or Audio File Path: ")))
    