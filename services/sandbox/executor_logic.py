import numpy as np
import sympy as sp
import math
from sympy.parsing.latex import parse_latex

def run_calculation(expression: str, mode: str = "eval", symbol: str = "x"):
    """
    Enhanced scientific calculation logic supporting symbolic reasoning and numerical analysis.
    """
    # 1. Environment Preparation
    if isinstance(__builtins__, dict):
        builtins_dict = __builtins__
    else:
        builtins_dict = vars(__builtins__)

    allowed_builtins = ['abs', 'min', 'max', 'round', 'len', 'sum', 'float', 'int', 'list', 'dict', 'range']
    safe_dict = {
        "np": np, 
        "sp": sp, 
        "math": math,
        "__builtins__": {k: builtins_dict[k] for k in allowed_builtins if k in builtins_dict}
    }

    try:
        # 2. Pre-processing: Auto-detect and handle LaTeX if necessary
        # If expression starts with '\', treat it as LaTeX
        if expression.strip().startswith('\\'):
            sympy_expr = parse_latex(expression)
        else:
            # Handle potential 'symbol' definition within raw strings
            sympy_expr = sp.sympify(expression)

        # 3. Modality Execution
        if mode == "solve":
            # Symbolic Solver
            var = sp.symbols(symbol)
            solution = sp.solve(sympy_expr, var)
            return [sp.latex(s) for s in solution] # Return LaTeX for better AI rendering
        
        elif mode == "simplify":
            # Symbolic Simplification (Crucial for academic derivation)
            return sp.latex(sp.simplify(sympy_expr))
            
        elif mode == "eval":
            # Numerical Evaluation or Direct Python Execution
            # Try evaluating with safe_dict
            result = eval(expression, safe_dict)
            
            # Handle NumPy array serialization
            if isinstance(result, (np.ndarray, np.generic)):
                return result.tolist()
            # Handle SymPy objects
            if hasattr(result, 'free_symbols'):
                return sp.latex(result)
            return result
        
        else:
            raise ValueError(f"Unsupported modality: {mode}")

    except Exception as e:
        raise RuntimeError(f"Calculation Logic Error: {str(e)}")