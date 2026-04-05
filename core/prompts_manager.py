from pathlib import Path
from jinja2 import Environment, FileSystemLoader

class PromptManager:
    def __init__(self):
        self.template_dir = Path(__file__).resolve().parent / "prompts"
        if not self.template_dir.exists():
            self.template_dir.mkdir(parents=True)
            
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )

    def render(self, template_name: str, **kwargs) -> str:
        template = self.env.get_template(f"{template_name}.jinja2")
        return template.render(**kwargs)

    def list_templates(self):
        return self.env.list_templates()