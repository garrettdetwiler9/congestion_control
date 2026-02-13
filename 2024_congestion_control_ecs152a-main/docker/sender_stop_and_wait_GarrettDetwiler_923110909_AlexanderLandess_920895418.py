import socket 
import time

PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
TIMEOUT = 0.5

FILE_PATH = f"./file.mp3"
RECEIVER_DEST = ("0.0.0.0", 5001)

def create_packet(seq_id, data):
    return int.to_bytes(seq_id, SEQ_ID_SIZE, signed=True, byteorder='big') + data

def send_packets(FILE_PATH, RECEIVER_DEST):

    # opens the file
    with open(FILE_PATH, 'rb') as f:
        
        # read the file's content
        data = f.read()
    
    # total number of bytes in the file's data
    total_byte_count = len(data)

    # creates an udp socket to send packets from
    # these parameters should match the same socket params in receiver.py
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        
        # bind the socket to a OS port
        # socket.bind((host, port))
        udp_socket.bind(('', 0))

        # sets the socket timeout (in seconds)
        udp_socket.settimeout(TIMEOUT)

        # used for performance metrics
        overall_start_timestamp = time.time()
        packet_delays = []

        # current packet's seq_id
        seq_id = 0

        # loops until all packets have been sent
        while seq_id < total_byte_count:

            # starts the inter-packet timer
            inter_start_timestamp = time.time()

            # gets the payload from data for the packet
            payload = data[seq_id:seq_id + MESSAGE_SIZE]

            # creates the packet
            packet = create_packet(seq_id, data=payload)

            # checks if the packet has been acked
            is_acked = False

            # sends packets 
            while not is_acked:

                # send the packet
                # .sendto(data, address)
                udp_socket.sendto(packet, RECEIVER_DEST)

                # waits for the ack packet before moving on
                try:
                    ack_packet, client = udp_socket.recvfrom(PACKET_SIZE)
                    ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')

                    # checks if this is the correct ack
                    if (ack_seq == seq_id + len(payload)):
                        
                        # tracks inter-packet delays
                        packet_delays.append(time.time() - inter_start_timestamp)

                        # moves onto the next packet
                        is_acked = True
                        seq_id += len(payload)
           
                # timeout means current packet needs to be retransmitted
                except socket.timeout:
                    continue
    
        # sends an empty byte message to indicate that all data has been sent
        packet = create_packet(seq_id, b'')
        finack_received = False
        
        # loops until finack is received
        while not finack_received:
            udp_socket.sendto(packet, RECEIVER_DEST)
            
            try:
                # wait for the ack and finack
                ack_packet, client = udp_socket.recvfrom(PACKET_SIZE)
                ack_seq = int.from_bytes(ack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                
                # validates the ack
                if ack_seq == seq_id:

                    # processes the received finack
                    finack_packet, client = udp_socket.recvfrom(PACKET_SIZE)
                    finack_seq = int.from_bytes(finack_packet[:SEQ_ID_SIZE], signed=True, byteorder='big')
                    
                    # validates the finack id
                    if finack_seq == seq_id + 3:

                        # sends the finack
                        finack_packet = create_packet(0, b'==FINACK==')
                        udp_socket.sendto(finack_packet, RECEIVER_DEST)
                        finack_received = True

            # timeout means current packet needs to be retransmitted
            except socket.timeout:
                continue
        
        # stops the overall timer
        overall_end_timestamp = time.time()
        total_time = overall_end_timestamp - overall_start_timestamp
    
    # calculates metrics
    avg_throughput = total_byte_count / total_time
    avg_packet_delay = sum(packet_delays) / len(packet_delays)
    avg_performance = 0.3 * (avg_throughput / 1000) + (0.7 / avg_packet_delay)

    return avg_throughput, avg_packet_delay, avg_performance


# output results
throughput, delay, performance = send_packets(FILE_PATH, RECEIVER_DEST)
print(f"{throughput:.7f}, {delay:.7f}, {performance:.7f}")