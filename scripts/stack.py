import os
import subprocess
from functools import reduce
from operator import concat

files = filter( lambda x: "webm" in x, os.listdir( "./" ) )
ins = map( lambda x: [ "-i", x ], files )
flatIns = list( reduce( concat, ins ) )

subprocess.run( [ "ffmpeg" ] + flatIns + [
    "-filter_complex", "[0:v][1:v][2:v][3:v]hstack=inputs=4[top];[4:v][5:v][6:v][7:v]hstack=inputs=4[bottom];[top][bottom]vstack=inputs=2[v]",
    "-map", "[v]",
    "-loop", "0",
    "-y",
    "stack.webm"
])
