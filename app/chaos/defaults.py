from .actions import DEFAULT_ACTIONS

def weights()->dict[str,float]: return {a.value:s.weight for a,s in DEFAULT_ACTIONS.items()}
