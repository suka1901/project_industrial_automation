ABB Robot Communication and Camera System
Project's Final Step: ABB Robot Communication and Camera System
Overview
This project provides:

Robot communication module (via socket connection)
Python socket server for PC–robot communication
Camera streaming utility for capturing video from a Basler camera, detecting ArUco markers, and calculating a pixel-to-millimeter ratio
These components allow you to:

Connect a PC to an ABB robot
Exchange data between the PC and robot
Display live camera feeds
Perform marker-based measurements
File Structure
File	Description
ServerCommuncatio.sys	Robot system file for enabling socket communication (upload to robot controller)
socket.py	Python TCP/IP server to communicate with the robot
Prerequisites
Python 3.11+
ABB RobotStudio
Basler Pylon SDK (for Basler camera)
Install Pylon Viewer: Basler Pylon ViewerLinks to an external site.
OpenCV 4.11+ with contrib modules:
pip install opencv-python
Setup Instructions
1. Upload Robot Files
Using RobotStudio, upload:

ServerCommuncatio.sys
Then load them onto the robot controller.

2. Network Configuration
Check PC IP address:
ipconfig
Check Robot IP address:
In RobotStudio when connected
Or on the teach pendant under Info → Network
Ensure both are on the same subnet:
PC:    192.168.125.2
Robot: 192.168.125.3
Netmask: 255.255.255.0
        
If not, change your PC’s Ethernet adapter to a static IP matching the robot’s subnet.

3. Running the Socket Server
Start the server:
python socket.py
When running, it will show:
Robot at address <IP> connected.
If you would like to end the program, enter 'quit'.
If you would like to send object data, enter 'sendData'.
        
Connect from the robot program.
4. Using the Camera Script
Connect the Basler camera.
Add ArUco instructions to the camera.py file:
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
parameters = cv2.aruco.DetectorParameters()
arucoDetector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
corners, ids, _ = arucoDetector.detectMarkers(img)
cv2.aruco.drawDetectedMarkers(img, corners)

# Calculate the perimeter of the first detected marker in pixels
aruco_perimeter = cv2.arcLength(corners[0], True)

# Calculate the pixel-to-millimeter ratio based on the known marker length
pixel_cm_ratio = aruco_perimeter / (aruco_length * 4)  # Divide by 4 sides of the square marker
aruco_length = 100  # mm
Run the script from Threading and Classes - Part Two.
The script will:
Show a live video feed
Detect 5x5 ArUco markers
Draw marker boundaries and IDs
Calculate a pixel-to-millimeter ratio based on a known marker size (default: 100 mm)
Press q to quit.