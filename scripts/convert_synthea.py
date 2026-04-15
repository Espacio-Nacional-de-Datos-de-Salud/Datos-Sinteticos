import io
import os
import subprocess

import pandas as pd
from tqdm import tqdm


def convert_lzo_to_parquet(source_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    files = [f for f in os.listdir(source_dir) if f.endswith(".lzo")]
    print(f"Found {len(files)} LZO files. Converting to Parquet...")

    for file_name in tqdm(files):
        full_path = os.path.join(source_dir, file_name)
        target_name = file_name.split(".")[0] + ".parquet"
        target_path = os.path.join(output_dir, target_name)

        try:
            # We call the system 'lzop' to decompress to stdout (-dc)
            # then capture that output into a buffer
            process = subprocess.run(["lzop", "-dc", full_path], capture_output=True, check=True)

            # Read the decompressed bytes as a CSV
            df = pd.read_csv(io.BytesIO(process.stdout), low_memory=False)

            # Save to Parquet
            df.to_parquet(target_path, index=False)

        except subprocess.CalledProcessError:
            print(f"Error: Is 'lzop' installed? Failed on {file_name}")
        except Exception as e:
            print(f"Failed to convert {file_name}: {e}")


if __name__ == "__main__":
    # Your current paths
    src = "./data/synthea100k"
    dest = "./data/synthea100k-processed"
    convert_lzo_to_parquet(src, dest)
