def move_mouse(x, y):
    screen_width, screen_height = pyautogui.size()
    pyautogui.moveTo(screen_width * x, screen_height * y)