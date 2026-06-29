import torch

print(f"PyTorch Version: {torch.__version__}")
print(f"CUDA verfügbar: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"CUDA Version: {torch.version.cuda}")
    print(f"GPU Name: {torch.cuda.get_device_name(0)}")
    print(f"Anzahl GPUs: {torch.cuda.device_count()}")
else:
    print("Kein CUDA verfügbar – Nutze CPU!")
