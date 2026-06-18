import os
import sys
# Make sure we can import google.genai
try:
    from google import genai
    from google.genai import types
    print("Has Behavior in types?", hasattr(types, "Behavior"))
    if hasattr(types, "FunctionDeclaration"):
        import inspect
        print("FunctionDeclaration sig:", inspect.signature(types.FunctionDeclaration))
    if hasattr(types, "Tool"):
        print("Tool sig:", inspect.signature(types.Tool))
except Exception as e:
    print("Error:", e)
