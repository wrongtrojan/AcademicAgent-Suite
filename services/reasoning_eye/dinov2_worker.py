import os
import json
import torch
import yaml
import numpy as np
from PIL import Image
import torchvision.transforms as T

class DINOv2Worker:
    def __init__(self):
        # 1. 自动定位并读取全局配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "../../configs/model_config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_config = yaml.safe_load(f)
        
        # 从 config 获取 dinov2 根目录
        self.model_root = self.full_config['model_paths']['dinov2']
        # 拼接你下载的 .pth 文件路径
        self.weight_path = os.path.join(self.model_root, "dinov2_vitl14_pretrain.pth")
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 2. 加载模型结构 (使用 torch.hub，pretrained=False 表示不在线下载权重)
        print(f"正在从本地加载 DINOv2 权重: {self.weight_path}")
        self.model = torch.hub.load('facebookresearch/dinov2', 'dinov2_vitl14', pretrained=False)
        
        # 3. 加载手动下载的 .pth 权重
        if not os.path.exists(self.weight_path):
            raise FileNotFoundError(f"未在指定路径找到权重文件: {self.weight_path}")
            
        self.model.load_state_dict(torch.load(self.weight_path, map_location='cpu'))
        self.model.to(self.device).eval()

        # 4. 定义 DINOv2 标准图像预处理
        self.transform = T.Compose([
            T.Resize(256, interpolation=T.InterpolationMode.BICUBIC),
            T.CenterCrop(224),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

    def process_images(self, image_dir):
        results = {}
        # 确保目录存在
        if not os.path.exists(image_dir):
            return results

        print(f"开始处理目录下的图片: {image_dir}")
        for img_name in os.listdir(image_dir):
            if img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                img_path = os.path.join(image_dir, img_name)
                try:
                    image = Image.open(img_path).convert("RGB")
                    img_tensor = self.transform(image).unsqueeze(0).to(self.device)
                    
                    with torch.no_grad():
                        # DINOv2 直接返回的就是 CLS Token 特征 (1024维)
                        embedding = self.model(img_tensor).cpu().numpy().flatten()
                    
                    results[img_name] = embedding.tolist()
                except Exception as e:
                    print(f"处理图片 {img_name} 出错: {e}")
                    
        return results

if __name__ == "__main__":
    import sys
    # 接收来自工具管理器的参数: python dinov2_worker.py <target_doc_id>
    if len(sys.argv) < 2:
        print("Usage: python dinov2_worker.py <doc_id>")
        sys.exit(1)

    doc_id = sys.argv[1]
    worker = DINOv2Worker()
    
    # 动态拼接 MinerU 处理后的图片路径
    processed_base = worker.full_config['paths']['processed_storage']
    target_image_dir = os.path.join(processed_base, doc_id, "images")
    
    features = worker.process_images(target_image_dir)
    
    # 将特征保存为临时 json，存放在文档处理目录下
    output_path = os.path.join(processed_base, doc_id, "chart_features.json")
    with open(output_path, "w") as f:
        json.dump(features, f)
    
    print(f"特征提取完成，已保存至: {output_path}")