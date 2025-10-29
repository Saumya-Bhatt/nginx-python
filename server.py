import socket
import selectors

from socket import socket as Socket

# =============================================================
# SETUP THE LISTENING SOCKET
# =============================================================

server_socket = socket.socket(
    family=socket.AF_INET,      # this means use IPv4
    type=socket.SOCK_STREAM     # open up a TCP connection
)

# this tells the server to reuse the port 8080 even after it restarts
server_socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)

server_socket.bind(("127.0.0.1", 8080))
server_socket.listen()
print("Listening on 127.0.0.1:8080")

# Sockets are blocking by default.
# By setting this flag, we're telling the kernel to not block incoming connections
# even if the existing ones are still being processed.
# We are relying on epoll to notify us once the existing requests are processed
server_socket.setblocking(False)




# =============================================================
# CREATE AN EPOLL INSTANCE (for windows, it is Selector)
# =============================================================

epoll = selectors.DefaultSelector()

# We register the socket with this epoll instance
# Now the kernel will notify us (the listening socket) once a READ_EVENT is available
epoll.register(
    fileobj=server_socket,
    events=selectors.EVENT_READ,
    data=None
)



# =============================================================
# STATE MANAGER TO MANAGE WHAT NEXT TO BE DONE WITH THE CLIENT CONNECTION (FD)
# =============================================================

# map [file_descriptor (int) : client_socket, handler_function]

handlers = {}


# --------- EVENT HANDLER FUNCTION --------------

def handle_accept():
    # once we have accepted the connection, this is when the actual File Descriptor is created
    client_socket, addr = server_socket.accept()
    print(f"Accepted connection from {addr}")
    client_socket.setblocking(False)

    # Register the client socket for listening to make accepting connection async
    epoll.register(
        fileobj=client_socket,
        events=selectors.EVENT_READ
    )
    handlers[client_socket.fileno()] = (client_socket, handle_client_read)


def handle_client_read(client_socket: Socket):
    try:
        data = client_socket.recv(1024)     # read only 1MB of data
        if data:
            print(f"Received: {data.decode().strip()}")
            # now that reading is done, register for writing
            epoll.modify(
                fileobj=client_socket,
                events=selectors.EVENT_WRITE
            )
            handlers[client_socket.fileno()] = (client_socket, handle_client_write)
        else:
            # client closed the connection
            close_client(client_socket)
    except ConnectionResetError:
        close_client(client_socket)


def handle_client_write(client_socket: Socket):
    client_socket.send(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nHello")
    close_client(client_socket)


def close_client(client_socket: Socket):
    fd = client_socket.fileno()
    print(f"Closing connection: fd={fd}")
    epoll.unregister(fd)
    handlers.pop(fd, None)
    try:
        client_socket.close()
    except OSError:
        print("Error closing client connection")
        pass



# =============================================================
# MAIN EVENT LOOP
# =============================================================

try:
    print("Web server started")
    while True:
        events = epoll.select(timeout=1)    # wait for upto 1s for any event
        for key, mask in events:
            sock = key.fileobj
            fd = key.fd

            if sock is server_socket:
                handle_accept()
            else:
                client_socket, handler = handlers.get(fd, (None, None))
                handler(client_socket)
except KeyboardInterrupt:
    print("Keyboard interruption detected")
finally:
    print("Shutting down web server...")
    epoll.unregister(server_socket.fileno())
    server_socket.close()
    print("Web server successfully shutdown")
