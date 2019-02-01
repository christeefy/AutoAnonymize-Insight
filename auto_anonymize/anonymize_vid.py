import time
import argparse
import warnings
from pathlib import Path
from functools import partial


import cv2
import numpy as np
import face_recognition
from pkg_utils import rgb_read, to_rgb
from viz import mark_faces_cv2, blur_faces
from face_detection.haar_cascade import detect_faces_hc
from face_detection.retinanet import detect_faces_ret, load_retinanet
from recognize_face import embed_face, recognize_face

def anonymize_vid(src, dst, known_faces_loc=None, 
                  use_retinanet=True, batch_size=1, profile=False):
    '''
    Anonymize a video by blurring unrecognized faces. 
    Writes a processed video to `dst`.

    Inputs:
        src:             Path to video.
        dst:             Path to save processsed video.
        known_faces_loc: Directory containing JPG images of 
                         recognized faces not to blur.
        use_retinanet:   Use RetinaNet (True) or 
                         Viola Jones algorithm (False).
        batch_size:      Process these number of images per batches.
        profile:         Profiles code execution time (Boolean). 

    Returns nothing.
    '''
    assert src.split('.')[-1].lower() in ['mov', 'mp4'], 'src is not a valid file.'
    assert dst.split('.')[-1].lower() == 'mp4', 'Output file format must be mp4.'

    # Record initial execution time
    if profile:
        start_time = time.time()

    # Define face detection function
    if use_retinanet:
        retinanet = load_retinanet()
        detect_fn = partial(detect_faces_ret, model=retinanet)
    else:
        detect_fn = detect_faces_hc

    # Load video and its metadata
    cap = cv2.VideoCapture(src)
    FRAME_HEIGHT = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    FRAME_WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    FRAME_COUNT = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Create video writer stream
    Path(dst).parent.mkdir(exist_ok=True, parents=True)
    out = cv2.VideoWriter(dst, 
          cv2.VideoWriter_fourcc(*'mp4v'), 30, (FRAME_WIDTH, FRAME_HEIGHT))

    # Get encodings of known faces
    perform_face_rec = False      # Boolean to perform facial recognition
    if known_faces_loc is not None:
        known_faces = [str(x) for x in Path(known_faces_loc).rglob('*.jpg')]
        if len(known_faces) == 0:
            warnings.warn('[WARNING] known_faces_loc contains no faces. JPG files only.')
        else:
            perform_face_rec = True
            # Create face encodings
            for filepath in known_faces:
                face_rgb = rgb_read(filepath)
                face_loc = detect_fn(face_rgb)
                recognized_face_encs = embed_face(face_rgb, face_loc)

    # Craete collector variables to store execution time
    if profile:
        detect_times = []
        recog_times = []

    # Video processing loop
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        rgb = to_rgb(frame)

        # Detect faces
        if profile:
            _detect_start = time.time()
            preds = detect_fn(rgb)
            detect_times.append(time.time() - _detect_start)
        else:
            preds = detect_fn(rgb)

        if len(preds):
            # Perform facial recognition
            # `recognized` is a boolean of recognized faces
            if perform_face_rec:
                if profile:
                    _recog_start = time.time()
                    face_encs = embed_face(rgb, preds)
                    recognized = recognize_face(face_encs, recognized_face_encs)
                    recog_times.append(time.time() - _recog_start)
                else:
                    face_encs = embed_face(rgb, preds)
                    recognized = recognize_face(face_encs, recognized_face_encs)

            # Add annotations on screen
            mark_faces_cv2(rgb, preds, recognized if perform_face_rec else None)
            rgb = blur_faces(rgb, preds, recognized if perform_face_rec else None,
                             'gaussian', (25, 25), 25)

        # Save frame
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        out.write(bgr)
    cap.release()

    # Summarize execution times
    if profile:
        end_time = time.time()
        print(f'\nTotal processing runtime: {end_time - start_time:.1f} sec for ' + \
              f'{FRAME_COUNT} frames ({FRAME_COUNT / (end_time - start_time):.1f} fps).')
        print(f'Average detection time: {np.mean(detect_times):.4f} sec per frame ' + \
              f'for {len(detect_times)} frames ({1/np.mean(detect_times):.1f} fps).')
        print(f'Average recognition time: {np.mean(recog_times):.4f} sec per frame' + \
              f'for {len(recog_times)} frames ({1/np.mean(recog_times):.1f} fps).')


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Script to anonymize faces in a video.')
    parser.add_argument('src', help='Path to video.')
    parser.add_argument('dst', help='Path to save processed video.')
    parser.add_argument('--known-faces-loc',
                        help='Directory containing JPG images of faces to not blur.')
    parser.add_argument('--use-viola-jones',
                        help='Use Viola Jones algorithm in lieu of RetinaNet' +
                             'for faster but less accurate face detection.',
                        dest='retinanet', action='store_false')
    parser.add_argument('--batch-size',
                        help='Batch process video frames for increased computation speed.' +
                             'Recommended for GPU only.', 
                        nargs='?', const=1, default=1, type=int)
    parser.add_argument('--profile', help='Boolean to profile code execution time.', 
                        action='store_true')

    args = parser.parse_args()
    return args


def main():
    args = parse_arguments()

    anonymize_vid(src=args.src, dst=args.dst, 
                  known_faces_loc=args.known_faces_loc,
                  use_retinanet=args.retinanet,
                  batch_size=args.batch_size,
                  profile=args.profile)


if __name__ == '__main__':
    main()