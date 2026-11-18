# LSB File-to-Image Steganography

## 1. Project Overview & Objective
This assignment hides the **entire contents of `secret.txt`** inside a carrier
image using **Least Significant Bit (LSB) steganography**, writes the stego
image, then recovers the hidden data into `recovered.txt` and verifies it is
byte-for-byte identical to the original. A PSNR measurement mathematically
confirms the image change is imperceptible.

| File | Purpose |
| --- | --- |
| `stego.py` | Self-contained script: embed, extract, verify, measure quality |
| `input.png` | Original carrier image |
| `secret.txt` | Secret file to hide (raw bytes, text or binary) |
| `output.png` | Stego image containing the hidden data |
| `recovered.txt` | File reconstructed from `output.png` |

## 2. Technique: LSB and Why PNG
The secret file's raw bytes are wrapped in a frame:
`[4-byte "STEG" signature][4-byte byte-length][secret bytes]`. Each bit is
written into the least-significant bit of the R, G and B channels, scanning
pixels left-to-right, top-to-bottom. Changing only the LSB moves any colour
value by at most **1 out of 255**, which is visually imperceptible.

**PNG is required** because it is lossless. Lossy formats such as JPEG alter
pixel values during compression and would destroy the embedded bits.

## 3. How to Run
Requirements: Python 3 and Pillow (`pip install pillow`).

```bash
python stego.py
```

The script reads `input.png` and `secret.txt`, creates `output.png` and
`recovered.txt`, compares the two files, and prints PSNR and SHA-256 digests.
Replace the sample `secret.txt` with your own confidential notes to hide
different data.

## 4. Dependencies & Libraries
| Library | Type | Used for in `stego.py` |
| --- | --- | --- |
| **Pillow (PIL)** | External (`pip install pillow`) | Opening and saving PNG images, per-pixel LSB access via `Image.load`, and computing the difference image for PSNR via `ImageChops.difference`. |
| `pathlib` | Python standard library | `Path` objects for all file paths, plus `exists()` and `stat()` checks for required files. |
| `math` | Python standard library | `math.log10()` in the PSNR formula `10·log10(255² / MSE)`. |
| `hashlib` | Python standard library | `sha256()` to produce the SHA-256 digests that confirm `recovered.txt` matches `secret.txt`. |

```bash
pip install pillow
```

## 5. Verification and Testing Results
Tested with Pillow 12.3.0 on a 559 x 357 RGB carrier and a 175-byte secret file.

| Check | Result |
| --- | --- |
| `recovered.txt` vs `secret.txt` | Identical byte-for-byte |
| SHA-256 digests | Match exactly |
| Output format / dimensions | PNG, 559 x 357 (unchanged) |
| Max per-channel pixel difference | 1 (LSBs only) |
| PSNR (input vs output) | **77.08 dB** |
| Repeated runs | Consistent results |

A PSNR above ~40 dB is generally considered visually lossless; 77.08 dB
confirms the steganography leaves the image effectively unchanged.
