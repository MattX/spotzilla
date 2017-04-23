import youtube_dl
import musicbrainzngs
from difflib import SequenceMatcher
import eyed3
import os
import shutil
import glob

CONFIDENCE_THRESHOLD = 0.8
TEMP_DIR = "/tmp/video_dl/"

def prepare_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    os.mkdir(path)


def similar(a, b):
        return SequenceMatcher(None, a, b).ratio()


class VariableHook:
    def __init__(self):
        self.hook = self.hookwarning

    def hookwarning(self, d):
        print("Warning: called unregistered hook!")

    def set_hook(self, h):
        self.hook = h

    def forward_hook(self, d):
        self.hook(d)


class Track:
    def __init__(self, fname, vid_title, title, artist, search_results, need_help):
        self.fname = fname
        self.vid_title = vid_title
        self.title = title
        self.artist = artist
        self.search_results = search_results
        self.need_help = need_help

    def write(self):
        l = eyed3.load(self.fname)
        if self.artist:
            l.tag.artist = self.artist
        if self.title:
            l.tag.title = self.title
        l.tag.save()


def download(url, ytdl, vh, tracks):
    """
    Do the heavy lifting
    """
    filename = None
    def hook(d):
        nonlocal filename
        if filename is None and d['status'] in ["downloading", "finished"]:
            filename = d['filename']
            print("Set filename to {}".format(d['filename']))
    vh.set_hook(hook)

    print("Downloading {}.".format(url))
    info = ytdl.extract_info(url, download=True)
    
    vid_title = info["title"]
    print("Video title is {}. Querying on musicbrainz...".format(vid_title))
    r = musicbrainzngs.search_recordings(vid_title)
    r = r['recording-list']

    track = Track(None, vid_title, None, None, r, True)
    presumed_title = None
    presumed_artist = None

    if len(r) == 0:
        print("No results found.")
        score = 0
    else:
        best_title = r[0]['title']
        best_artist = r[0]['artist-credit'][0]['artist']['name']
        print("Best found: {} - {}. ".format(best_artist, best_title), end="")
        parts = [p.strip() for p in vid_title.split("-")]
        if len(parts) == 1:
            presumed_title = parts[0]
            score = similar(presumed_title, best_title)
        elif len(parts) == 2:
            presumed_artist = parts[0]
            presumed_title = parts[1]
            score = max(similar(parts[0], best_title) + similar(parts[1], best_artist),
                        similar(parts[1], best_title) + similar(parts[0], best_artist)) / 2
        else:
            score = 0

        print("Confidence: {:.0f}%. ".format(score*100), end="")

    # Spin just in case the hook hasn't been called
    while filename is None:
        pass

    track.fname = filename

    if score > CONFIDENCE_THRESHOLD:
        print("Saving information.")
        track.artist = best_artist
        track.title = best_title
        track.need_help = False
        track.write()
    else:
        print("I'll need some help.")
        track.artist = presumed_artist
        track.title = presumed_title

    tracks.append(track)


musicbrainzngs.set_useragent("Music Consolidator", "1.0", "matthieufelix@gmail.com")

vh = VariableHook()
ydl_opts = {
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            }],
        'progress_hooks': [vh.forward_hook],
        }

tracks = []

prepare_dir(TEMP_DIR)

import sys
with youtube_dl.YoutubeDL(ydl_opts) as ytdl:
    for track in sys.argv[1:]:
        download(track, ytdl, vh, tracks)
        print()

print("Downloading done.")

for track in tracks:
    if track.need_help:
        continue
    
    print("Track {}: wrote as {} - {}.".format(track.vid_title, track.artist, track.title))


for track in tracks:
    if not track.need_help:
        continue

    print("Track {}:".format(track.vid_title))
    in_artist = input("  Artist [{}]? ".format(track.artist)).strip()
    if in_artist:
        track.artist = in_artist

    in_title = input("  Title [{}]? ".format(track.title)).strip()
    if in_title:
        track.title = in_title

    track.write()

print("All set.")

