"""
PSRL integration: agent loop, Harbor runner, reward, and failure classification.

Nothing is re-exported here. PSRL resolves `_target_` and `agent_name` by dotted
path, and eager imports would pull Harbor into every process that touches the
package.
"""
