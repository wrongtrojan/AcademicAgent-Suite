import os
import tarfile
import subprocess
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "0"
from huggingface_hub import hf_hub_download, logging

logging.set_verbosity_info()

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ID = "wrongtrojan/AcademicAgent-Suite"
TOKEN = None  

FILES = [
    "VisualInference.tar.gz", 
    "DocRecognize.tar.gz", 
    "AgentLogic.tar.gz",
    "VideoRecognize.tar.gz", 
    "SandboxInference.tar.gz", 
    "DataStream.tar.gz"
]

def download_and_extract():
    print(f"Initialization: Accessing repository {REPO_ID}")
    
    for file_name in FILES:
        # Step 1: Download
        print(f"\nTask Started: Downloading {file_name}")
        try:
            downloaded_path = hf_hub_download(
                repo_id=REPO_ID,
                filename=file_name,
                repo_type="dataset",
                token=TOKEN,
                local_dir=BASE_DIR
            )
            print(f"Status: Download of {file_name} completed successfully.")

            # Step 2: Extract
            folder_name = file_name.replace(".tar.gz", "")
            abs_extract_dir = os.path.join(BASE_DIR, folder_name)
            
            if not os.path.exists(abs_extract_dir):
                os.makedirs(abs_extract_dir)

            print(f"Task Started: Extracting {file_name} to {abs_extract_dir}/")
            with tarfile.open(downloaded_path, "r:gz") as tar:
                tar.extractall(path=abs_extract_dir)
            print(f"Status: Extraction of {file_name} completed.")

            # --- 新增 Step 2.5: Conda Unpack ---
            unpack_script = os.path.join(abs_extract_dir, "bin", "conda-unpack")
            if os.path.exists(unpack_script):
                print(f"Task Started: Running conda-unpack for {folder_name}...")
                try:
                    # 使用 subprocess 执行脚本，确保在环境目录下运行
                    result = subprocess.run(
                        [unpack_script], 
                        cwd=abs_extract_dir, 
                        capture_output=True, 
                        text=True
                    )
                    if result.returncode == 0:
                        print(f"Status: Conda-unpack for {file_name} completed successfully.")
                    else:
                        print(f"Warning: Conda-unpack finished with issues: {result.stderr}")
                except Exception as unpack_e:
                    print(f"Warning: Failed to execute conda-unpack: {unpack_e}")
            else:
                print(f"Notice: No conda-unpack script found in {folder_name}/bin, skipping.")

            # Step 3: Cleanup
            if os.path.exists(downloaded_path):
                os.remove(downloaded_path)
                print(f"Cleanup: Removed archive {file_name} to conserve disk space.")

        except Exception as e:
            print(f"Error: Operation failed for {file_name}. Details: {e}")

    print("\nFinal Status: All processes finished.")

if __name__ == "__main__":
    download_and_extract()