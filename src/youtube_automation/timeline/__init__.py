"""Timeline and Scene-Graph package.

Provides single-source-of-truth timeline management and hierarchical scene-graph modeling.
"""

from .scene_graph import MacroScene, SceneBeat, SceneGraph

__all__ = ["MacroScene", "SceneBeat", "SceneGraph"]
