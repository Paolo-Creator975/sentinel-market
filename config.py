import json

def load_config(path="config.json"):
    with open(path,"r",encoding="utf-8") as f: cfg=json.load(f)
    if cfg.get("mode")!="HISTORICAL": raise RuntimeError("Questa build accetta solo modalità HISTORICAL.")
    return cfg
