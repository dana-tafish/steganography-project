"""
stego.py - File-to-image LSB steganography using Pillow.

The entire contents of 'secret.txt' are treated as binary data and hidden in
the least-significant bits of 'input.png'. The result is saved as 'output.png',
then the hidden bytes are recovered into 'recovered.txt' and checked against
the original file. A PSNR measurement is also reported to show that the image
change is imperceptible.

Payload frame written into the image:

    [ 4-byte magic "STEG" ][ 4-byte byte-length ][ N raw secret bytes ]

Every bit of that frame is stored in the least-significant bit of the R, G and
B channels, scanning pixels left-to-right / top-to-bottom. Only the LSB changes,
so no colour value moves by more than 1 out of 255.

PNG is used because it is lossless - lossy formats such as JPEG would destroy
the embedded bits.

Run with:  python stego.py
"""

import hashlib
import math
from pathlib import Path

from PIL import Image, ImageChops

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
INPUT_PATH = Path("input.png")        # carrier image supplied with the assignment
OUTPUT_PATH = Path("output.png")      # stego image, always written as PNG
SECRET_PATH = Path("secret.txt")      # file whose raw bytes will be hidden
RECOVERED_PATH = Path("recovered.txt")  # file reconstructed from the stego image

MAGIC = b"STEG"  # signature used to recognise our payload when extracting


# --------------------------------------------------------------------------- #
# Bit-level helpers
# --------------------------------------------------------------------------- #
def bytes_to_bits(data: bytes):
    """Yield the bits of *data*, most-significant bit first."""
    for byte in data:
        for shift in range(7, -1, -1):
            yield (byte >> shift) & 1


def bits_to_bytes(bits):
    """Group an iterable of bits into bytes, most-significant bit first."""
    current = 0
    filled = 0
    for bit in bits:
        current = (current << 1) | (bit & 1)
        filled += 1
        if filled == 8:
            yield current
            current = 0
            filled = 0


def read_exact_bytes(bit_iterator, byte_count: int) -> bytes:
    """Read exactly *byte_count* bytes from an iterator of bits.

    If the iterator is exhausted early, the partially collected byte (if any)
    is padded on the right with zeros. This prevents crashes on truncated data.
    """
    result = bytearray()
    current = 0
    filled = 0

    for _ in range(byte_count * 8):
        try:
            bit = next(bit_iterator)
        except StopIteration:
            if filled:
                result.append((current << (8 - filled)) & 0xFF)
            return bytes(result)

        current = (current << 1) | (bit & 1)
        filled += 1
        if filled == 8:
            result.append(current)
            current = 0
            filled = 0

    return bytes(result)


def iter_lsb_bits(image: Image.Image):
    """Yield the least-significant bit of every R, G and B channel.

    Pixels are visited in standard row-major order (top-left to bottom-right).
    """
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y][:3]
            yield r & 1
            yield g & 1
            yield b & 1


# --------------------------------------------------------------------------- #
# Embedding / extraction
# --------------------------------------------------------------------------- #
def embed_file(input_path: Path, output_path: Path, secret_path: Path) -> None:
    """Hide the raw bytes of *secret_path* inside *input_path*."""
    secret_bytes = secret_path.read_bytes()
    payload = MAGIC + len(secret_bytes).to_bytes(4, "big") + secret_bytes
    bits = list(bytes_to_bits(payload))

    # Work in RGB so every pixel has exactly three writable channels.
    with Image.open(input_path) as source:
        image = source.convert("RGB")

    width, height = image.size
    capacity_bits = width * height * 3
    if len(bits) > capacity_bits:
        raise ValueError(
            f"Secret file is too large: need {len(bits)} bits but the image "
            f"only holds {capacity_bits} bits ({capacity_bits // 8} bytes)."
        )

    pixels = image.load()
    bit_index = 0
    total_bits = len(bits)

    # Overwrite only the LSB of each colour channel, leaving the upper 7 bits
    # (and therefore the visible colour) untouched.
    for y in range(height):
        for x in range(width):
            channels = list(pixels[x, y][:3])
            for i in range(3):
                if bit_index < total_bits:
                    channels[i] = (channels[i] & 0xFE) | bits[bit_index]
                    bit_index += 1
            pixels[x, y] = tuple(channels)
            if bit_index >= total_bits:
                break
        if bit_index >= total_bits:
            break

    # PNG is lossless, so the embedded bits survive the save intact.
    image.save(output_path, format="PNG")


def extract_to_file(image_path: Path, recovered_path: Path) -> bytes:
    """Recover hidden bytes from *image_path*, write them to disk, return them."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")

    bit_stream = iter_lsb_bits(image)

    magic = read_exact_bytes(bit_stream, len(MAGIC))
    if magic != MAGIC:
        raise ValueError(
            "No hidden file found (unexpected signature). "
            "Make sure you are reading the generated output.png."
        )

    length = int.from_bytes(read_exact_bytes(bit_stream, 4), "big")
    capacity_bytes = (image.size[0] * image.size[1] * 3) // 8
    if length <= 0 or length > capacity_bytes:
        raise ValueError(f"Invalid hidden file length: {length} bytes.")

    secret_bytes = read_exact_bytes(bit_stream, length)
    recovered_path.write_bytes(secret_bytes)
    return secret_bytes


# --------------------------------------------------------------------------- #
# Quality verification
# --------------------------------------------------------------------------- #
def verify_imperceptibility(original_path: Path, stego_path: Path) -> None:
    """Print PSNR and the maximum per-channel pixel change between two images.

    PSNR = 10 * log10(MAX^2 / MSE), with MAX = 255 for 8-bit channels. Since LSB
    steganography only ever changes a channel value by 1, MSE is extremely small
    and PSNR is very high (well above the ~40 dB "visually lossless" threshold).
    """
    with Image.open(original_path) as a, Image.open(stego_path) as b:
        original = a.convert("RGB")
        stego = b.convert("RGB")

    if original.size != stego.size:
        raise ValueError("Cannot compare images with different dimensions.")

    difference = ImageChops.difference(original, stego)
    # An RGB histogram is 768 bins: 0-255 = R, 256-511 = G, 512-767 = B.
    # The error magnitude is the bin index *within its channel*, not the raw
    # index, so each channel must be read with its own 256-bin offset.
    histogram = difference.histogram()
    squared_error = sum(
        (value * value) * histogram[channel * 256 + value]
        for channel in range(3)
        for value in range(256)
    )
    channel_count = original.width * original.height * 3
    max_delta = max(
        value
        for channel in range(3)
        for value in range(256)
        if histogram[channel * 256 + value]
    )

    if squared_error == 0:
        psnr = float("inf")
    else:
        mse = squared_error / channel_count
        psnr = 10.0 * math.log10((255.0 * 255.0) / mse)

    psnr_text = "infinite (identical images)" if math.isinf(psnr) else f"{psnr:.2f} dB"
    print(f"[*] PSNR (input.png vs output.png): {psnr_text}")
    print(f"[*] Maximum per-channel pixel difference: {max_delta}")

    if max_delta <= 1:
        print("[OK] Only least-significant bits changed - visually imperceptible.")
    else:
        print("[WARNING] Unexpected pixel differences detected.")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    for required in (INPUT_PATH, SECRET_PATH):
        if not required.exists():
            raise FileNotFoundError(f"Required file '{required}' not found.")

    print(f"[*] Carrier image : {INPUT_PATH}")
    print(f"[*] Secret file   : {SECRET_PATH} ({SECRET_PATH.stat().st_size} bytes)")

    embed_file(INPUT_PATH, OUTPUT_PATH, SECRET_PATH)
    print(f"[+] Secret embedded. Saved stego image as '{OUTPUT_PATH}' (PNG).")

    recovered = extract_to_file(OUTPUT_PATH, RECOVERED_PATH)
    original = SECRET_PATH.read_bytes()
    print(f"[+] Hidden data extracted to '{RECOVERED_PATH}' ({len(recovered)} bytes).")

    if recovered == original:
        print("[OK] File verification successful: recovered.txt matches secret.txt byte-for-byte.")
    else:
        print("[ERROR] File verification FAILED: recovered data does not match.")

    # Cryptographic confirmation of the byte-for-byte check above.
    print(f"[*] SHA-256 secret.txt   : {hashlib.sha256(original).hexdigest()}")
    print(f"[*] SHA-256 recovered.txt: {hashlib.sha256(recovered).hexdigest()}")

    verify_imperceptibility(INPUT_PATH, OUTPUT_PATH)


if __name__ == "__main__":
    main()
