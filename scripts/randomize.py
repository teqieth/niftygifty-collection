import collections
import json
import os
import subprocess
import random
import hashlib
import threading
import logging
import concurrent.futures


seed = 7391
rand = random.Random()
rand.seed( seed )

collectionSize = 12
workerCount = 12
useSwapBuffer = True
convertToGif = True
dryRun = False
outExtension = ".webm"
suffix = ""
outFolder = "out/"
codecArgs = [
    # "-qp", "0",
    # "-tune", "animation",
    # "-crf", "0",
    # "-loop", "0",
    # "-c:v", "libx264",
    # "-preset", "veryslow",
    "-c:v", "libvpx-vp9",
    "-lossless", "1"
]

backgroundDir = "assets/backgrounds"
giftDir = "assets/gifts"
charDir = "assets/characters"

lock = threading.Lock()
hashes = set()
collection = {
    "seed": seed,
    "size": collectionSize,
    "items": []
}

backgrounds = {}
gifts = {}
characters = {}

logging.basicConfig( format='%(message)s', encoding='utf-8', level=logging.INFO )


def parseWeightedFiles( directory ):
    infoPath = os.path.join( directory, "info.json" )
    infos = {}

    if os.path.exists( infoPath ):
        with open( infoPath ) as fin:
            infos = json.load( fin )

    files = list( filter( lambda x: not x.endswith( ".json" ), os.listdir( directory ) ))
    weights = [ ( infos[ f ][ "weight" ] if ( f in infos ) and "weight" in infos[ f ] else 100 ) for f in files ]
    return { "files": files, "weights": weights }


def parseAssets():
    global backgrounds
    global gifts
    global characters

    backgrounds = parseWeightedFiles( backgroundDir )
    gifts = parseWeightedFiles( giftDir )
    characters = parseWeightedFiles( charDir )
    characters[ "items" ] = {}

    for char in os.listdir( charDir ): #  "Hovering Wizard"
        if char.endswith( ".json" ): continue
        logging.debug( char )
        charPath = os.path.join( charDir, char )   #  "assets/characters/Hovering Wizard"
        charInfoPath = os.path.join( charPath, "info.json" )   #  "assets/characters/Hovering Wizard/info.json"
        charInfos = {}
        characters[ "items" ][ char ] = {}

        if os.path.exists( charInfoPath ):
            with open( charInfoPath ) as fin:
                charInfos = json.load( fin )

        for layer in os.listdir( charPath ):    #  "hat addon (optional)"
            if layer.endswith( ".json" ): continue
            logging.debug( "  %s", layer )
            layerPath = os.path.join( charPath, layer ) #  "assets/characters/Hovering Wizard/hat addon (optional)"
            filesAndWeights = parseWeightedFiles( layerPath )
            prob = charInfos[ layer ][ "probability" ] if ( layer in charInfos ) else 1.0
            characters[ "items" ][ char ][ layer ] = { "probability": prob } | filesAndWeights
            logging.debug( "  %s: %s", layer, filesAndWeights[ "files" ] )

        logging.debug( "" )


def printAssets():
    global backgrounds
    global gifts
    global characters

    logging.info(  "backgrounds" )
    logging.debug( "   files:   %s", backgrounds[ "files" ] )
    logging.info(  "   weights: %s", backgrounds[ "weights" ] )

    logging.info(  "gifts" )
    logging.debug( "   files:   %s", gifts[ "files" ] )
    logging.info(  "   weights: %s", gifts[ "weights" ] )

    logging.info(  "characters" )
    logging.info(  "    weights: %s", characters[ "weights" ] )
    for char, layers in characters[ "items" ].items():
        logging.info( "    %s", char )
        for layer, infos in layers.items():
            logging.info(  "        %s", layer )
            logging.debug( "            infos: %s", infos )
            logging.debug( "            files:       %s", infos[ "files" ] )
            logging.info(  "            weights:     %s", infos[ "weights" ] )
            logging.info(  "            probability: %s", infos[ "probability" ] )


def chooseLayers():
    global lock
    global hashes
    global collection
    global rand

    #  randomly select weighted layers in order

    backgroundFile = rand.choices( backgrounds[ "files" ], backgrounds[ "weights" ] )[ 0 ]
    giftFile = rand.choices( gifts[ "files" ], gifts[ "weights" ] )[ 0 ]

    order = []
    order.append( os.path.normcase( os.path.join( backgroundDir, backgroundFile )))
    order.append( os.path.normcase( os.path.join( giftDir, giftFile )))

    charItems = characters[ "items" ]
    charName = rand.choices( list( charItems.keys() ), characters[ "weights" ] )[ 0 ]
    layers = charItems[ charName ]

    for layerName, infos in sorted( layers.items(), key=lambda x: int( x[0].split( ' ' )[ 1 ] ) ):
        if rand.random() > infos[ "probability" ]: continue
        layerFile = rand.choices( infos[ "files"], infos[ "weights" ] )[ 0 ]
        filePath = os.path.normcase( os.path.join( charDir, charName, layerName, layerFile ) )
        order.append( filePath )

    order = list( map( lambda x: x.replace( '\\', '/' ), order ))

    #  compute combined hash

    lock.acquire()

    m = hashlib.shake_256()
    for x in order: m.update( x.encode( 'utf-8' ) )
    itemHash = m.hexdigest( 32 )
    hasItem = ( itemHash in hashes )
    if not hasItem:
        collection[ "items" ].append({
            "files": order,
            "id": len( hashes ),
            "hash": itemHash
        })
    hashes.add( itemHash )
    itemCount = len( hashes )

    lock.release()

    if hasItem:
        logging.warning( "item already exists (#%s)", itemHash )
        return False, itemHash

    logging.debug( "%i - %s", itemCount, itemHash )
    return itemHash, order


def composeLayers( item ):
    itemId = str( item[ "id" ] ).rjust( 4, '0' )
    order = item[ "files" ]
    logging.info( "compositing %s (0x%s)...", itemId, item[ "hash" ][ :8 ] )

    fileBase = outFolder + itemId
    resultFile = fileBase + suffix + outExtension
    resultGif = fileBase + suffix + ".gif"
    tempFiles = [
        fileBase + "_tempA" + outExtension,
        fileBase + "_tempB" + outExtension
    ]
    tempId = 0
    tempOutFile = ""

    for i in range( 1, len( order ) ):
        prevFile = tempFiles[ tempId ] if useSwapBuffer else fileBase + "_temp" + str( i ) + outExtension
        p1 = order[ 0 ] if i == 1 else prevFile
        p2 = order[ i ]
        tempId = ( tempId + 1 ) % 2
        tempOutFile = tempFiles[ tempId ] if useSwapBuffer else fileBase + "_temp" + str( i + 1 ) + outExtension
        args = [
            "ffmpeg",
            "-i", p1,
            "-i", p2,
            "-filter_complex", "overlay=1",
            "-y"
        ]
        args.extend( codecArgs )
        args.append( tempOutFile )
        subprocess.run( args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT )

    #  rename and clean up temp files
    args = [ "mv", tempOutFile, resultFile ]
    subprocess.run( args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT )

    tempId = ( tempId + 1 ) % 2
    subprocess.run( [ "rm", tempFiles[ tempId ] ] )

    #  convert to gif
    if convertToGif:
        args = [
            "ffmpeg",
            "-i", resultFile,
            "-vf", "fps=30,scale=-1:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:reserve_transparent=0[p];[s1][p]paletteuse",
            "-y",
            resultGif
        ]
        subprocess.run( args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT )

    return True, item[ "id" ]


def main():
    parseAssets()
    # printAssets()

    if not os.path.exists( outFolder ):
        os.mkdir( outFolder )

    while len( hashes ) < collectionSize:
        chooseLayers()

    with open( os.path.join( outFolder, "collection.json" ), 'w' ) as fout:
        json.dump( collection, fout, sort_keys=True, indent=4 )

    if dryRun: return

    with concurrent.futures.ThreadPoolExecutor( max_workers=workerCount ) as executor:
        executor.map( composeLayers, collection[ "items" ] )


main()