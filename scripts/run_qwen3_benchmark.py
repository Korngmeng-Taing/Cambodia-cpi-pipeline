import os
import sys
os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
os.environ['OLLAMA_MODEL'] = 'qwen3:8b'
os.environ['PYTHONUTF8'] = '1'
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Run the benchmark by importing it
import importlib.util
script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evaluate_accuracy_benchmark.py')
spec = importlib.util.spec_from_file_location("benchmark", script_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.main()
