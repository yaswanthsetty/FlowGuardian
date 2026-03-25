import socket

# Server details (replace with receiver's IP if on another device)
HOST = "10.99.33.210"  # Use actual IP if sending over LAN/Wi-Fi
PORT = 5000

# Create socket and connect
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((HOST, PORT))
print(f"✅ Connected to {HOST}:{PORT}")

# Send data
while True:
    msg = input("✉️ Enter message (or 'exit' to quit): ")
    if msg.lower() == "exit":
        break
    client_socket.sendall(msg.encode())
    print("📤 Message sent!")

client_socket.close()
print("🔴 Connection closed.")
