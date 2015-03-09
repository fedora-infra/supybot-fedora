import socket
hostname = socket.gethostname()

config = dict(
    endpoints={
        "supybot.%s" % hostname: [
            "tcp://127.0.0.1:6009",
        ],
    },
)
