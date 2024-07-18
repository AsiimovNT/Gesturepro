import csv
import copy
import argparse
import itertools
from collections import Counter, deque

import cv2 as cv
import numpy as np
import mediapipe as mp
import pyautogui
import os
import subprocess
# Uncomment for Windows
# from ctypes import cast, POINTER
# from comtypes import CLSCTX_ALL
# from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from utils import CvFpsCalc
from model import KeyPointClassifier
from model import PointHistoryClassifier

def get_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--width", help='cap width', type=int, default=960)
    parser.add_argument("--height", help='cap height', type=int, default=540)

    parser.add_argument('--use_static_image_mode', action='store_true')
    parser.add_argument("--min_detection_confidence",
                        help='min_detection_confidence',
                        type=float,
                        default=0.7)
    parser.add_argument("--min_tracking_confidence",
                        help='min_tracking_confidence',
                        type=int,
                        default=0.5)

    args = parser.parse_args()

    return args

# Helper functions for volume control (Linux)
def change_volume(direction):
    if direction == 'down':
        os.system("amixer -D pulse sset Master 5%-")
    elif direction == 'up':
        os.system("amixer -D pulse sset Master 5%+")
    
     

# For Windows, uncomment and use this function
# def change_volume(direction):
#     devices = AudioUtilities.GetSpeakers()
#     interface = devices.Activate(
#         IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
#     volume = cast(interface, POINTER(IAudioEndpointVolume))
#     current_volume = volume.GetMasterVolumeLevelScalar()
#     if direction == "down":
#         volume.SetMasterVolumeLevelScalar(max(current_volume - 0.05, 0.0), None)

def move_mouse(x, y, click=False):
    screen_width, screen_height = pyautogui.size()
    pyautogui.moveTo(screen_width * x, screen_height * y)

    if click:
        pyautogui.click()
        
            
def main():
    args = get_args()

    cap_device = args.device
    cap_width = args.width
    cap_height = args.height

    use_static_image_mode = args.use_static_image_mode
    min_detection_confidence = args.min_detection_confidence
    min_tracking_confidence = args.min_tracking_confidence

    use_brect = True

    cap = cv.VideoCapture(cap_device)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, cap_width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, cap_height)

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        static_image_mode=use_static_image_mode,
        max_num_hands=1,
        min_detection_confidence=min_detection_confidence,
        min_tracking_confidence=min_tracking_confidence,
    )

    keypoint_classifier = KeyPointClassifier()
    point_history_classifier = PointHistoryClassifier()

    with open('model/keypoint_classifier/keypoint_classifier_label.csv', encoding='utf-8-sig') as f:
        keypoint_classifier_labels = csv.reader(f)
        keypoint_classifier_labels = [row[0] for row in keypoint_classifier_labels]
    with open('model/point_history_classifier/point_history_classifier_label.csv', encoding='utf-8-sig') as f:
        point_history_classifier_labels = csv.reader(f)
        point_history_classifier_labels = [row[0] for row in point_history_classifier_labels]

    cvFpsCalc = CvFpsCalc(buffer_len=10)

    history_length = 16
    point_history = deque(maxlen=history_length)
    finger_gesture_history = deque(maxlen=history_length)

    mode = 0

    while True:
        fps = cvFpsCalc.get()
        key = cv.waitKey(10)
        if key == 27:  # ESC
            break
        number, mode = select_mode(key, mode)

        ret, image = cap.read()
        if not ret:
            break
        image = cv.flip(image, 1)
        debug_image = copy.deepcopy(image)
        image = cv.cvtColor(image, cv.COLOR_BGR2RGB)
        image.flags.writeable = False
        results = hands.process(image)
        image.flags.writeable = True

        if results.multi_hand_landmarks is not None:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                brect = calc_bounding_rect(debug_image, hand_landmarks)
                landmark_list = calc_landmark_list(debug_image, hand_landmarks)
                pre_processed_landmark_list = pre_process_landmark(landmark_list)
                pre_processed_point_history_list = pre_process_point_history(debug_image, point_history)

                logging_csv(number, mode, pre_processed_landmark_list, pre_processed_point_history_list)

                hand_sign_id = keypoint_classifier(pre_processed_landmark_list)
                if hand_sign_id == 2:  # Pointing gesture
                    point_history.append(landmark_list[8])
                else:
                    point_history.append([0, 0])

                # Implement mouse movement on a pointing gesture
                if hand_sign_id == 3:  # Replace with your specific gesture ID
                    x, y = landmark_list[8]
                    move_mouse(x / cap_width, y / cap_height)

                finger_gesture_id = 0
                point_history_len = len(pre_processed_point_history_list)
                if point_history_len == (history_length * 2):
                    finger_gesture_id = point_history_classifier(pre_processed_point_history_list)

                # Control volume based on finger gesture ID
                if finger_gesture_id == 1:  # "Clockwise" gesture ID
                    change_volume("down")
                if finger_gesture_id == 2:
                    change_volume("up")

                finger_gesture_history.append(finger_gesture_id)
                most_common_fg_id = Counter(finger_gesture_history).most_common()

                debug_image = draw_bounding_rect(use_brect, debug_image, brect)
                debug_image = draw_landmarks(debug_image, landmark_list)
                debug_image = draw_info_text(debug_image, brect, handedness, keypoint_classifier_labels[hand_sign_id], point_history_classifier_labels[most_common_fg_id[0][0]])

        else:
            point_history.append([0, 0])

        debug_image = draw_point_history(debug_image, point_history)
        debug_image = draw_info(debug_image, fps, mode, number)

        cv.imshow('Hand Gesture Recognition', debug_image)

    cap.release()
    cv.destroyAllWindows()
    
    
def calc_bounding_rect(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_array = np.empty((0, 2), int)

    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point = [np.array((landmark_x, landmark_y))]

        landmark_array = np.append(landmark_array, landmark_point, axis=0)

    x, y, w, h = cv.boundingRect(landmark_array)

    return [x, y, x + w, y + h]

def calc_landmark_list(image, landmarks):
    image_width, image_height = image.shape[1], image.shape[0]

    landmark_point = []

    for _, landmark in enumerate(landmarks.landmark):
        landmark_x = min(int(landmark.x * image_width), image_width - 1)
        landmark_y = min(int(landmark.y * image_height), image_height - 1)

        landmark_point.append([landmark_x, landmark_y])

    return landmark_point

def pre_process_landmark(landmark_list):
    temp_landmark_list = copy.deepcopy(landmark_list)

    # Convert to relative coordinates
    base_x, base_y = 0, 0
    for index, landmark_point in enumerate(temp_landmark_list):
        if index == 0:
            base_x, base_y = landmark_point[0], landmark_point[1]

        temp_landmark_list[index][0] = temp_landmark_list[index][0] - base_x
        temp_landmark_list[index][1] = temp_landmark_list[index][1] - base_y

    # Convert to a one-dimensional list
    temp_landmark_list = list(
        itertools.chain.from_iterable(temp_landmark_list))

    # Normalization
    max_value = max(list(map(abs, temp_landmark_list)))

    def normalize_(n):
        return n / max_value

    temp_landmark_list = list(map(normalize_, temp_landmark_list))

    return temp_landmark_list

def pre_process_point_history(image, point_history):
    image_width, image_height = image.shape[1], image.shape[0]

    temp_point_history = copy.deepcopy(point_history)

    # Convert to relative coordinates
    base_x, base_y = 0, 0
    for index, point in enumerate(temp_point_history):
        if index == 0:
            base_x, base_y = point[0], point[1]

        temp_point_history[index][0] = (temp_point_history[index][0] - base_x) / image_width
        temp_point_history[index][1] = (temp_point_history[index][1] - base_y) / image_height

    # Convert to a one-dimensional list
    temp_point_history = list(
        itertools.chain.from_iterable(temp_point_history))

    return temp_point_history

def logging_csv(number, mode, landmark_list, point_history_list):
    if mode == 0:
        pass
    if mode == 1 and (0 <= number <= 9):
        csv_path = 'model/keypoint_classifier/keypoint.csv'
        with open(csv_path, 'a', newline="") as f:
            writer = csv.writer(f)
            writer.writerow([number, *landmark_list])
    if mode == 2 and (0 <= number <= 9):
        csv_path = 'model/point_history_classifier/point_history.csv'
        with open(csv_path, 'a', newline="") as f:
            writer = csv.writer(f)
            writer.writerow([number, *point_history_list])

def draw_bounding_rect(use_brect, image, brect):
    if use_brect:
        cv.rectangle(image, (brect[0], brect[1]), (brect[2], brect[3]), (0, 255, 0), 2)

    return image

def draw_landmarks(image, landmark_point):
    if len(landmark_point) > 0:
        # Palm
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[1]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[5]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[9]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[13]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[17]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[0]), tuple(landmark_point[17]), (0, 255, 0), 2)

        # Fingers
        cv.line(image, tuple(landmark_point[1]), tuple(landmark_point[2]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[2]), tuple(landmark_point[3]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[3]), tuple(landmark_point[4]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[5]), tuple(landmark_point[6]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[6]), tuple(landmark_point[7]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[7]), tuple(landmark_point[8]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[9]), tuple(landmark_point[10]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[10]), tuple(landmark_point[11]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[11]), tuple(landmark_point[12]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[13]), tuple(landmark_point[14]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[14]), tuple(landmark_point[15]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[15]), tuple(landmark_point[16]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[17]), tuple(landmark_point[18]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[18]), tuple(landmark_point[19]), (0, 255, 0), 2)
        cv.line(image, tuple(landmark_point[19]), tuple(landmark_point[20]), (0, 255, 0), 2)

    return image

def draw_point_history(image, point_history):
    for index, point in enumerate(point_history):
        if point[0] != 0 and point[1] != 0:
            cv.circle(image, tuple(point), 2, (0, 255, 0), 2)
    return image

def draw_info(image, fps, mode, number):
    cv.putText(image, "FPS:" + str(fps), (10, 30), cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv.LINE_AA)
    mode_string = ['Logging Key Point', 'Logging Point History']
    if 0 <= mode <= 2:
        cv.putText(image, "MODE:" + mode_string[mode], (10, 60), cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv.LINE_AA)
    if 0 <= number <= 9:
        cv.putText(image, "NUM:" + str(number), (10, 90), cv.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv.LINE_AA)
    return image

def draw_info_text(image, brect, handedness, hand_sign_text, finger_gesture_text):
    cv.rectangle(image, (brect[0], brect[1] - 22), (brect[2], brect[1]), (0, 255, 0), -1)
    cv.putText(image, "Handedness:" + handedness.classification[0].label[0:], (brect[0] + 5, brect[1] - 4), cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv.LINE_AA)
    if hand_sign_text != "":
        cv.putText(image, "Hand Gesture:" + hand_sign_text, (brect[0] + 5, brect[1] - 4), cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv.LINE_AA)
    if finger_gesture_text != "":
        cv.putText(image, "Finger Gesture:" + finger_gesture_text, (brect[0] + 5, brect[1] - 4), cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv.LINE_AA)
    return image

def select_mode(key, mode):
    number = -1
    if 48 <= key <= 57:  # 0 ~ 9
        number = key - 48

    if key == 110:  # n
        mode = 0
    if key == 107:  # k
        mode = 1
    if key == 104:  # h
        mode = 2

    return number, mode

# Rest of the functions (select_mode, calc_bounding_rect, etc.) remain unchanged

if __name__ == '__main__':
    main()

# Helper functions (make sure these are defined in your code)

