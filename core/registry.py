# core/registry.py
# Module capability registry.
# A module is a class with:
#   - name: str
#   - load(config, bus) -> None    called at startup
#   - unload() -> None             called at shutdown (optional)
#   - set_llm(llm) -> None         optional, called if module needs Ollama access


class Registry:
    def __init__(self):
        self._modules: dict = {}

    def register(self, module):
        self._modules[module.name] = module

    def load_all(self, config: dict, bus):
        module_config = config.get("modules", {})
        for name, mod in self._modules.items():
            if module_config.get(name, {}).get("enabled", True):
                print(f"[registry] Loading module: {name}")
                mod.load(config, bus)

    def unload_all(self):
        for mod in self._modules.values():
            if hasattr(mod, "unload"):
                mod.unload()

    def get(self, name: str):
        return self._modules.get(name)


registry = Registry()
