import cv2
import numpy as np
import pyautogui
from cvzone.HandTrackingModule import HandDetector

# Initialize webcam
cap = cv2.VideoCapture(0)
cap.set(3, 1280)
cap.set(4, 720)

# Initialize hand detector
detector = HandDetector(detectionCon=0.8, maxHands=1)

# Variables
prev_locations_x = []
prev_locations_y = []
smoothing = 5  # Number of points to average

# Screen size
wScreen, hScreen = pyautogui.size()

while True:
    # Get image from webcam
    success, img = cap.read()
    if not success:
        break
    
    # Find hand and its landmarks
    hands, img = detector.findHands(img)
    if hands:
        lmList = hands[0]['lmList']
        bbox = hands[0]['bbox']
        fingers = detector.fingersUp(hands[0])

        # Get the tip of the index finger
        x, y = lmList[8][0], lmList[8][1]

        # Add the location to the list
        prev_locations_x.append(x)
        prev_locations_y.append(y)

        # Maintain only the last 'smoothing' number of positions
        if len(prev_locations_x) > smoothing:
            prev_locations_x.pop(0)
            prev_locations_y.pop(0)

        # Calculate the average of the positions
        avg_x = np.mean(prev_locations_x)
        avg_y = np.mean(prev_locations_y)

        # Move mouse
        pyautogui.moveTo(wScreen - avg_x, avg_y)
        cv2.circle(img, (lmList[8][0], lmList[8][1]), 15, (255, 0, 255), cv2.FILLED)

        if fingers == [0, 1, 0, 0, 0]:
            length, info, img = detector.findDistance(lmList[8][0:2], lmList[12][0:2], img, draw=True)

            if length < 25:
                cv2.circle(img, (lmList[8][0], lmList[8][1]), 15, (0, 255, 0), cv2.FILLED)
                pyautogui.click()

    cv2.imshow("Img", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
