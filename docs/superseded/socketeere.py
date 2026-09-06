import socket  # Import Python's socket library for network communication.

# Define a function to send data to the robot and receive a response.
def sendToRobot(sendData):
    server_message = sendData  # Store the message to send in a variable (could send directly).
    
    # Send the message to the connected client (robot) after encoding it to UTF-8 bytes.
    client_socket.send(server_message.encode("UTF-8"))
    print("send Objekt !")  # Confirmation in terminal that data was sent.

    # Wait for a response from the robot and print it to the terminal.
    if client_socket.recv:  # Check if the socket's recv method is available (this always returns True; likely unnecessary).
        print("the message is:")  # Info message before displaying the robot's response.
        
        # Receive up to 4094 bytes of data from the robot.
        client_message = client_socket.recv(4094)
        
        # Decode the received bytes from Latin-1 encoding into a string.
        client_message = client_message.decode("latin-1")
        
        # Print the robot's response to the terminal.
        print("!!", client_message)
    
    # Return the received message back to the caller for further use.
    return client_message

# Main program entry point
if __name__ == '__main__':
    # Create a TCP/IP socket for the server.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Bind the socket to a specific IP address and port (server will listen here).
    server_socket.bind(('192.168.125.2', 5000))
    
    # Start listening for incoming connections.
    server_socket.listen()
    
    # Accept a new incoming connection from a client (robot).
    # This call blocks until a connection is made.
    (client_socket, client_ip) = server_socket.accept()
    
    # Print the IP address of the connected robot.
    print(f"Robot at address {client_ip} connected.")
    
    # Instructions for the user about program commands.
    print("If you would like to end the program, enter 'quit'.")
    print("If you would like to send object data, enter 'sendData'.")
    
    # Send an initial message to the robot to confirm the connection.
    client_message = sendToRobot("connection exists")
