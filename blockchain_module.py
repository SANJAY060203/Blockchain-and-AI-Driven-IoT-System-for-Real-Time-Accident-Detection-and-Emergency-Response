import json
import hashlib
import os
from datetime import datetime

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

class Blockchain:
    def __init__(self, chain_file=None, key_file=None):
        # Set the storage path to your pendrive location.
        storage_path = r"C:\Users\Sanjay\OneDrive\Desktop\emergency response system\EDGE"
        if chain_file is None:
            chain_file = os.path.join(storage_path, "blockchain.json")
        if key_file is None:
            key_file = os.path.join(storage_path, "private_key.pem")
        self.chain_file = chain_file
        self.key_file = key_file
        self.chain = []
        self.private_key = None
        self.public_key = None
        self.load_or_create_keys()  # This also exports the public key to public_key.pem
        if os.path.exists(self.chain_file):
            try:
                with open(self.chain_file, 'r') as f:
                    self.chain = json.load(f)
            except Exception as e:
                print("Error loading blockchain file:", e)
                self.chain = []
                self.create_genesis_block()
                self.save_chain()
        else:
            self.chain = []
            self.create_genesis_block()
            self.save_chain()

    def load_or_create_keys(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as key_file:
                self.private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                    backend=default_backend()
                )
            self.public_key = self.private_key.public_key()
        else:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self.public_key = self.private_key.public_key()
            with open(self.key_file, 'wb') as key_file:
                pem = self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
                key_file.write(pem)
        # Export and save the public key to the same storage path as the private key
        self.export_public_key()

    def export_public_key(self):
        public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        # Save the public key in the same directory as the private key, with the name "public_key.pem"
        public_key_file = os.path.join(os.path.dirname(self.key_file), "public_key.pem")
        with open(public_key_file, "wb") as f:
            f.write(public_key_pem)
        # Optionally, print out the public key for reference
        print("Public Key:")
        print(public_key_pem.decode('utf-8'))

    def create_genesis_block(self):
        genesis_data = {
            'incident_id': '0',
            'data': 'Genesis Block'
        }
        genesis_block = self.create_block(genesis_data, previous_hash="0", index=0)
        self.chain.append(genesis_block)

    def create_block(self, data, previous_hash, index):
        block = {
            'index': index,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'incident_id': str(index),
            'data': data,
            'previous_hash': previous_hash,
            'nonce': 0
        }
        block = self.proof_of_work(block)
        block['signature'] = self.sign_block(block)
        return block

    def compute_hash(self, block):
        block_copy = block.copy()
        block_copy.pop('hash', None)
        block_copy.pop('signature', None)
        block_string = json.dumps(block_copy, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def proof_of_work(self, block, difficulty=4):
        prefix_str = '0' * difficulty
        while True:
            block_hash = self.compute_hash(block)
            if block_hash.startswith(prefix_str):
                block['hash'] = block_hash
                return block
            else:
                block['nonce'] += 1

    def sign_block(self, block):
        block_hash = block['hash'].encode()
        signature = self.private_key.sign(
            block_hash,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return signature.hex()

    def add_block(self, data):
        previous_block = self.chain[-1]
        new_index = previous_block['index'] + 1
        new_block = self.create_block(data, previous_block['hash'], new_index)
        self.chain.append(new_block)
        self.save_chain()

    def save_chain(self):
        try:
            with open(self.chain_file, 'w') as f:
                json.dump(self.chain, f, indent=4)
        except Exception as e:
            print("Error saving blockchain file:", e)
