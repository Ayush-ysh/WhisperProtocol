"""Tests for WhisperProtocol Cryptography Layer (Milestone D)."""

import time
import struct
import pytest

from whisper.crypto import (
    generate_keypair,
    export_public_key,
    load_public_key,
    derive_shared_secret,
    derive_session_keys,
    compute_sas_only,
    encrypt_gcm,
    decrypt_gcm,
    encrypt_and_pack,
    unpack_and_decrypt,
    pack_encrypted_payload,
    unpack_encrypted_payload,
    CryptoSession,
    SessionRole,
    SessionState,
    CryptoError,
    KeyExchangeError,
    SASNotVerifiedError,
    SASRejectedError,
    SessionExpiredError,
    SessionNotActiveError,
    ReplayAttackError,
    DecryptionError,
    InvalidNonceError,
    X25519_KEY_LEN,
    GCM_OVERHEAD,
)
from whisper.protocol.frames import (
    create_transfer_offer,
    create_transfer_accept,
    create_data_frame,
    encode_protocol_frame,
    decode_protocol_frame,
    FrameType,
)


class TestX25519KeyAgreement:
    """Tests for X25519 key generation, serialization, and Diffie-Hellman exchange."""

    def test_generate_keypair(self):
        priv, pub_bytes = generate_keypair()
        assert len(pub_bytes) == X25519_KEY_LEN
        assert isinstance(pub_bytes, bytes)

    def test_key_exchange_symmetry(self):
        alice_priv, alice_pub = generate_keypair()
        bob_priv, bob_pub = generate_keypair()

        shared_alice = derive_shared_secret(alice_priv, bob_pub)
        shared_bob = derive_shared_secret(bob_priv, alice_pub)

        assert len(shared_alice) == 32
        assert len(shared_bob) == 32
        assert shared_alice == shared_bob

    def test_invalid_public_key_length(self):
        priv, _ = generate_keypair()
        with pytest.raises(KeyExchangeError, match="Invalid X25519 public key length"):
            derive_shared_secret(priv, b"\x00" * 31)

        with pytest.raises(KeyExchangeError, match="Invalid X25519 public key length"):
            derive_shared_secret(priv, b"\x00" * 33)

    def test_invalid_public_key_type(self):
        priv, _ = generate_keypair()
        with pytest.raises(KeyExchangeError, match="Public key must be bytes"):
            derive_shared_secret(priv, "not-bytes")  # type: ignore

    def test_distinct_keypairs(self):
        _, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        assert pub1 != pub2


class TestHKDFDerivation:
    """Tests for HKDF session key derivation and 6-digit Short Authentication String (SAS)."""

    def test_session_keys_derivation(self):
        shared_secret = b"\x42" * 32
        sender_pub = b"\x01" * 32
        receiver_pub = b"\x02" * 32

        keys = derive_session_keys(
            shared_secret=shared_secret,
            sender_pub=sender_pub,
            receiver_pub=receiver_pub,
        )

        assert len(keys.sender_key) == 32
        assert len(keys.receiver_key) == 32
        assert keys.sender_key != keys.receiver_key

    def test_sas_format_and_range(self):
        shared_secret = b"\x77" * 32
        sender_pub = b"\xaa" * 32
        receiver_pub = b"\xbb" * 32

        keys = derive_session_keys(shared_secret, sender_pub=sender_pub, receiver_pub=receiver_pub)

        assert len(keys.raw_sas) == 6
        assert keys.raw_sas.isdigit()
        assert len(keys.sas_code) == 7
        assert keys.sas_code[3] == "-"
        assert keys.sas_code[:3].isdigit()
        assert keys.sas_code[4:].isdigit()
        assert 0 <= keys.sas_numeric < 1_000_000

    def test_hkdf_consistency_between_peers(self):
        alice_priv, alice_pub = generate_keypair()
        bob_priv, bob_pub = generate_keypair()

        shared_alice = derive_shared_secret(alice_priv, bob_pub)
        shared_bob = derive_shared_secret(bob_priv, alice_pub)

        # Both define Alice as Sender and Bob as Receiver
        alice_keys = derive_session_keys(shared_alice, sender_pub=alice_pub, receiver_pub=bob_pub)
        bob_keys = derive_session_keys(shared_bob, sender_pub=alice_pub, receiver_pub=bob_pub)

        assert alice_keys.sender_key == bob_keys.sender_key
        assert alice_keys.receiver_key == bob_keys.receiver_key
        assert alice_keys.sas_code == bob_keys.sas_code
        assert alice_keys.sas_numeric == bob_keys.sas_numeric

    def test_salt_and_transcript_domain_separation(self):
        shared = b"\x11" * 32
        pub_a = b"\x01" * 32
        pub_b = b"\x02" * 32

        keys1 = derive_session_keys(shared, salt=b"salt-1", sender_pub=pub_a, receiver_pub=pub_b)
        keys2 = derive_session_keys(shared, salt=b"salt-2", sender_pub=pub_a, receiver_pub=pub_b)

        assert keys1.sender_key != keys2.sender_key
        assert keys1.sas_code != keys2.sas_code


class TestAESGCMEncryption:
    """Tests for AES-256-GCM authenticated encryption and decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        key = b"\x55" * 32
        plaintext = b"Acoustic encrypted transmission through air"
        aad = b"session=0x1234,seq=1"

        ciphertext, nonce, tag = encrypt_gcm(plaintext, key, aad=aad)
        assert len(nonce) == 12
        assert len(tag) == 16
        assert len(ciphertext) == len(plaintext)
        assert ciphertext != plaintext

        decrypted = decrypt_gcm(ciphertext, key, nonce, tag, aad=aad)
        assert decrypted == plaintext

    def test_aad_mismatch_fails_decryption(self):
        key = b"\x55" * 32
        plaintext = b"Sensitive payload"

        ciphertext, nonce, tag = encrypt_gcm(plaintext, key, aad=b"correct-aad")

        with pytest.raises(DecryptionError, match="tampered"):
            decrypt_gcm(ciphertext, key, nonce, tag, aad=b"wrong-aad")

    def test_ciphertext_tampering_fails(self):
        key = b"\x55" * 32
        plaintext = b"Sensitive payload"

        ciphertext, nonce, tag = encrypt_gcm(plaintext, key)
        tampered_ct = bytearray(ciphertext)
        tampered_ct[0] ^= 0x01

        with pytest.raises(DecryptionError):
            decrypt_gcm(bytes(tampered_ct), key, nonce, tag)

    def test_tag_tampering_fails(self):
        key = b"\x55" * 32
        plaintext = b"Sensitive payload"

        ciphertext, nonce, tag = encrypt_gcm(plaintext, key)
        tampered_tag = bytearray(tag)
        tampered_tag[-1] ^= 0xFF

        with pytest.raises(DecryptionError):
            decrypt_gcm(ciphertext, key, nonce, bytes(tampered_tag))

    def test_pack_and_unpack_helpers(self):
        key = b"\x77" * 32
        plaintext = b"Packed payload binary test"
        aad = b"session=42"

        packed = encrypt_and_pack(plaintext, key, aad=aad)
        assert len(packed) == GCM_OVERHEAD + len(plaintext)

        decrypted = unpack_and_decrypt(packed, key, aad=aad)
        assert decrypted == plaintext

    def test_short_payload_fails_unpacking(self):
        key = b"\x77" * 32
        with pytest.raises(DecryptionError, match="Packed payload too short"):
            unpack_and_decrypt(b"short", key)

    def test_invalid_key_length(self):
        with pytest.raises(CryptoError, match="32-byte key"):
            encrypt_gcm(b"data", b"too-short")

    def test_invalid_nonce_length(self):
        key = b"\x00" * 32
        with pytest.raises(InvalidNonceError):
            encrypt_gcm(b"data", key, nonce=b"bad_nonce")


class TestCryptoSessionLifecycle:
    """Tests for full CryptoSession state machine, SAS confirmation, and anti-replay."""

    def test_alice_bob_full_session_flow(self):
        session_id = 0xCAFEBABE

        # 1. Initialize
        alice = CryptoSession(session_id=session_id, role=SessionRole.SENDER)
        bob = CryptoSession(session_id=session_id, role=SessionRole.RECEIVER)

        assert alice.state == SessionState.INITIALIZING
        assert bob.state == SessionState.INITIALIZING

        # 2. Key Exchange
        alice_sas = alice.establish_peer_key(bob.local_public_key)
        bob_sas = bob.establish_peer_key(alice.local_public_key)

        assert alice.state == SessionState.SAS_PENDING
        assert bob.state == SessionState.SAS_PENDING
        assert alice_sas == bob_sas

        # 3. Explicit User Confirmation on both sides
        alice.confirm_sas(True)
        bob.confirm_sas(True)

        assert alice.state == SessionState.ACTIVE
        assert bob.state == SessionState.ACTIVE

        # 4. Secure Sender -> Receiver payload transfer
        payload_msg = b"Offline ultrasonic air-gap transmission verified"
        aad_data = alice.build_aad(FrameType.DATA_FRAME, seq_num=1)

        packed_out = alice.encrypt_outgoing(payload_msg, aad=aad_data)
        decrypted_in = bob.decrypt_incoming(packed_out, aad=aad_data)

        assert decrypted_in == payload_msg

        # 5. Secure Receiver -> Sender ACK/reply
        ack_msg = b"TRANSFER_ACK_AUTHENTICATED"
        aad_ack = bob.build_aad(FrameType.TRANSFER_ACK, seq_num=1)

        packed_ack = bob.encrypt_outgoing(ack_msg, aad=aad_ack)
        decrypted_ack = alice.decrypt_incoming(packed_ack, aad=aad_ack)

        assert decrypted_ack == ack_msg

    def test_premature_encryption_blocked_by_sas_gate(self):
        session = CryptoSession(session_id=1, role=SessionRole.SENDER)
        _, bob_pub = generate_keypair()

        # In INITIALIZING state
        with pytest.raises(SessionNotActiveError):
            session.encrypt_outgoing(b"premature data")

        # In SAS_PENDING state
        session.establish_peer_key(bob_pub)
        with pytest.raises(SASNotVerifiedError, match="requires user confirmation"):
            session.encrypt_outgoing(b"premature data")

    def test_premature_decryption_blocked_by_sas_gate(self):
        alice = CryptoSession(session_id=1, role=SessionRole.SENDER)
        bob = CryptoSession(session_id=1, role=SessionRole.RECEIVER)
        alice.establish_peer_key(bob.local_public_key)
        bob.establish_peer_key(alice.local_public_key)

        # In SAS_PENDING state before confirmation
        dummy_packed = b"\x00" * 40
        with pytest.raises(SASNotVerifiedError):
            bob.decrypt_incoming(dummy_packed)

    def test_rejected_sas_blocks_transfer(self):
        alice = CryptoSession(session_id=1, role=SessionRole.SENDER)
        bob = CryptoSession(session_id=1, role=SessionRole.RECEIVER)
        alice.establish_peer_key(bob.local_public_key)
        bob.establish_peer_key(alice.local_public_key)

        # Alice user rejects SAS
        alice.confirm_sas(False)
        assert alice.state == SessionState.SAS_REJECTED

        with pytest.raises(SASRejectedError, match="SAS verification was rejected"):
            alice.encrypt_outgoing(b"data")

    def test_anti_replay_nonce_detection(self):
        session_id = 123
        alice = CryptoSession(session_id=session_id, role=SessionRole.SENDER)
        bob = CryptoSession(session_id=session_id, role=SessionRole.RECEIVER)
        alice.establish_peer_key(bob.local_public_key)
        bob.establish_peer_key(alice.local_public_key)
        alice.confirm_sas(True)
        bob.confirm_sas(True)

        packed = alice.encrypt_outgoing(b"Single-use message")
        # First arrival succeeds
        decrypted = bob.decrypt_incoming(packed)
        assert decrypted == b"Single-use message"

        # Replay of exact same message must be rejected
        with pytest.raises(ReplayAttackError, match="Replay attack detected"):
            bob.decrypt_incoming(packed)

    def test_session_expiration(self):
        alice = CryptoSession(session_id=999, role=SessionRole.SENDER, ttl_seconds=0.05)
        _, bob_pub = generate_keypair()
        alice.establish_peer_key(bob_pub)
        alice.confirm_sas(True)

        assert not alice.is_expired
        time.sleep(0.06)
        assert alice.is_expired

        with pytest.raises(SessionExpiredError):
            alice.encrypt_outgoing(b"expired payload")

    def test_directional_key_isolation(self):
        """Verify Alice cannot decrypt her own outgoing ciphertext with her incoming key."""
        session_id = 555
        alice = CryptoSession(session_id=session_id, role=SessionRole.SENDER)
        bob = CryptoSession(session_id=session_id, role=SessionRole.RECEIVER)
        alice.establish_peer_key(bob.local_public_key)
        bob.establish_peer_key(alice.local_public_key)
        alice.confirm_sas(True)
        bob.confirm_sas(True)

        packed_out = alice.encrypt_outgoing(b"Hello from Alice")
        # Alice tries to decrypt with her own incoming key (which is receiver_key)
        with pytest.raises(DecryptionError):
            alice.decrypt_incoming(packed_out)

    def test_session_status_telemetry(self):
        session = CryptoSession(session_id=0x11223344, role=SessionRole.SENDER)
        status = session.get_status()
        assert status["session_id"] == 0x11223344
        assert status["role"] == "sender"
        assert status["state"] == "initializing"
        assert status["is_expired"] is False
        assert status["sas_code"] is None
        assert "private_key" not in status


class TestProtocolFrameCryptoIntegration:
    """Tests integrating CryptoSession with canonical protocol frames."""

    def test_full_protocol_crypto_handshake(self):
        session_id = 0x55AA1122

        # 1. Ephemeral key generation
        sender_session = CryptoSession(session_id=session_id, role=SessionRole.SENDER)
        receiver_session = CryptoSession(session_id=session_id, role=SessionRole.RECEIVER)

        # 2. Sender creates TRANSFER_OFFER carrying public key
        offer_frame = create_transfer_offer(
            file_name="secret_plan.txt",
            file_size=42,
            session_id=session_id,
            public_key=sender_session.local_public_key,
        )
        offer_bits = encode_protocol_frame(offer_frame)

        # Receiver receives and decodes TRANSFER_OFFER
        decoded_offer = decode_protocol_frame(offer_bits)
        assert decoded_offer.frame_type == FrameType.TRANSFER_OFFER

        # Receiver unpacks offer payload: name_len(1B) + name + size(4B) + pubkey(32B)
        offer_p = decoded_offer.payload
        name_len = offer_p[0]
        extracted_name = offer_p[1 : 1 + name_len].decode("utf-8")
        extracted_size = struct.unpack(">I", offer_p[1 + name_len : 5 + name_len])[0]
        sender_pubkey = offer_p[5 + name_len : 37 + name_len]

        assert extracted_name == "secret_plan.txt"
        assert extracted_size == 42
        assert sender_pubkey == sender_session.local_public_key

        # 3. Receiver establishes sender's key and answers with TRANSFER_ACCEPT
        receiver_sas = receiver_session.establish_peer_key(sender_pubkey)
        accept_frame = create_transfer_accept(
            session_id=session_id,
            public_key=receiver_session.local_public_key,
        )
        accept_bits = encode_protocol_frame(accept_frame)

        # Sender receives and decodes TRANSFER_ACCEPT
        decoded_accept = decode_protocol_frame(accept_bits)
        receiver_pubkey = decoded_accept.payload[:32]
        sender_sas = sender_session.establish_peer_key(receiver_pubkey)

        # 4. SAS Matching verification
        assert sender_sas == receiver_sas
        sender_session.confirm_sas(True)
        receiver_session.confirm_sas(True)

        # 5. Encrypted DATA_FRAME transmission
        secret_content = b"TOP_SECRET_AIRGAP_PAYLOAD_2026"
        seq_num = 1
        aad = sender_session.build_aad(FrameType.DATA_FRAME, seq_num)
        encrypted_packed = sender_session.encrypt_outgoing(secret_content, aad=aad)

        data_frame = create_data_frame(
            session_id=session_id,
            seq_num=seq_num,
            data=encrypted_packed,
        )
        data_bits = encode_protocol_frame(data_frame)

        # Receiver receives DATA_FRAME
        decoded_data_frame = decode_protocol_frame(data_bits)
        assert decoded_data_frame.frame_type == FrameType.DATA_FRAME
        assert decoded_data_frame.seq_num == seq_num

        # Receiver decrypts and authenticates
        rx_aad = receiver_session.build_aad(decoded_data_frame.frame_type, decoded_data_frame.seq_num)
        decrypted_payload = receiver_session.decrypt_incoming(decoded_data_frame.payload, aad=rx_aad)

        assert decrypted_payload == secret_content
