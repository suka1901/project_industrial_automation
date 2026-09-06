import socket  # Python's socket library for network communication.

VALID_SHAPES = ["square", "circle", "triangle", "hexagon", "star"]


def sendToRobot(client_socket, sendData):
    """Send a command string to the robot and return its text response."""
    client_socket.send(sendData.encode("UTF-8"))
    print(f"Sent to robot: {sendData}")

    client_message = client_socket.recv(4094)
    client_message = client_message.decode("UTF-8")  # matches the encoding used to send

    print("Robot says:", client_message)
    return client_message


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("192.168.125.201", 5000))
    server_socket.listen()

    (client_socket, client_ip) = server_socket.accept()
    print(f"Robot at address {client_ip} connected.")

    print("Commands:")
    print("  sendData  - send a 'move <shape>' command to the robot")
    print("  quit      - tell the robot to disconnect and stop this program")

    try:
        while True:
            user_input = input("\nEnter command (send/quit): ").strip().lower()

            if user_input == "quit":
                sendToRobot(client_socket, "quit")
                break

            elif user_input == "send":
                shape = input(
                    f"Enter shape to move ({'/'.join(VALID_SHAPES)}): "
                ).strip().lower()

                if shape not in VALID_SHAPES:
                    print(f"'{shape}' is not a recognized shape. Try again.")
                    continue

                sendToRobot(client_socket, f"move {shape}")

            else:
                print("Unknown command. Please enter 'send' or 'quit'.")

    finally:
        client_socket.close()
        server_socket.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
