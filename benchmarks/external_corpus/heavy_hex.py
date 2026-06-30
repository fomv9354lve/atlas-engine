"""IBM Eagle r3 127-qubit heavy-hex coupling map + kicked transverse-field Ising
(Floquet) circuit generator, as run in Kim et al., Nature 618, 500 (2023)
("Evidence for the utility of quantum computing before fault tolerance").

The coupling map below is the canonical 127-qubit Eagle heavy-hex lattice shared
by ibm_kyiv / ibm_sherbrooke / ibm_brisbane (the device class Kim et al. used).
We validate it structurally at import (127 nodes, one connected component, max
degree 3 = heavy-hex signature) so we never silently emit a wrong topology.

The Kim et al. circuit is a Trotterized kicked Ising Floquet evolution:
  per Trotter step:  Rzz(2*theta_J) on every heavy-hex edge,  then  Rx(phi) on every qubit.
The "utility" demonstration used theta_J = -pi/2 (the maximally entangling ZZ
angle) and swept phi; the hard regime is phi near pi/2. This was later reproduced
classically by tensor-network methods (Tindall, Fishman, Stoudenmire, Sels,
PRX Quantum 5, 020332 (2024), "Efficient tensor network simulation of IBM's
Eagle kicked Ising experiment"), and by several other groups (Begusic & Chan;
Liao et al.; Patra et al.) -- i.e. it was field-assumed-QPU-hard but is
classically reachable.
"""
from __future__ import annotations
import math

# Canonical IBM Eagle (127-qubit) heavy-hex coupling map (undirected edges).
EAGLE_127_EDGES = [
    # horizontal row 0 (qubits 0..13)
    [0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7],[7,8],[8,9],[9,10],[10,11],[11,12],[12,13],
    # vertical bridges row0 -> row1
    [0,14],[14,18],[4,15],[15,22],[8,16],[16,26],[12,17],[17,30],
    # horizontal row 1 (18..32)
    [18,19],[19,20],[20,21],[21,22],[22,23],[23,24],[24,25],[25,26],[26,27],[27,28],[28,29],[29,30],[30,31],[31,32],
    # vertical bridges row1 -> row2
    [20,33],[33,39],[24,34],[34,43],[28,35],[35,47],[32,36],[36,51],
    # horizontal row 2 (37..51)
    [37,38],[38,39],[39,40],[40,41],[41,42],[42,43],[43,44],[44,45],[45,46],[46,47],[47,48],[48,49],[49,50],[50,51],
    # vertical bridges row2 -> row3
    [37,52],[52,56],[41,53],[53,60],[45,54],[54,64],[49,55],[55,68],
    # horizontal row 3 (56..70)
    [56,57],[57,58],[58,59],[59,60],[60,61],[61,62],[62,63],[63,64],[64,65],[65,66],[66,67],[67,68],[68,69],[69,70],
    # vertical bridges row3 -> row4
    [58,71],[71,77],[62,72],[72,81],[66,73],[73,85],[70,74],[74,89],
    # horizontal row 4 (75..89)
    [75,76],[76,77],[77,78],[78,79],[79,80],[80,81],[81,82],[82,83],[83,84],[84,85],[85,86],[86,87],[87,88],[88,89],
    # vertical bridges row4 -> row5
    [75,90],[90,94],[79,91],[91,98],[83,92],[92,102],[87,93],[93,106],
    # horizontal row 5 (94..108)
    [94,95],[95,96],[96,97],[97,98],[98,99],[99,100],[100,101],[101,102],[102,103],[103,104],[104,105],[105,106],[106,107],[107,108],
    # vertical bridges row5 -> row6
    [96,109],[109,114],[100,110],[110,118],[104,111],[111,122],[108,112],[112,126],
    # horizontal row 6 (113..126)
    [113,114],[114,115],[115,116],[116,117],[117,118],[118,119],[119,120],[120,121],[121,122],[122,123],[123,124],[124,125],[125,126],
]

N_EAGLE = 127


def _validate():
    nodes = set()
    deg = {}
    for a, b in EAGLE_127_EDGES:
        nodes.add(a); nodes.add(b)
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    assert nodes == set(range(N_EAGLE)), f"nodes != 0..126: missing {set(range(N_EAGLE))-nodes}, extra {nodes-set(range(N_EAGLE))}"
    maxdeg = max(deg.values())
    assert maxdeg <= 3, f"max degree {maxdeg} > 3 (not heavy-hex)"
    # single connected component
    adj = {i: [] for i in range(N_EAGLE)}
    for a, b in EAGLE_127_EDGES:
        adj[a].append(b); adj[b].append(a)
    seen = {0}; stack = [0]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v); stack.append(v)
    assert len(seen) == N_EAGLE, f"graph not connected: {len(seen)}/{N_EAGLE} reachable"
    return maxdeg, len(EAGLE_127_EDGES)


MAX_DEGREE, N_EDGES = _validate()


def kicked_ising_qasm(n_steps: int = 5, theta_J: float = -math.pi / 2,
                      phi: float = math.pi / 2) -> str:
    """OpenQASM 2.0 for the Kim et al. kicked-Ising Floquet circuit on the
    127-qubit Eagle heavy-hex map.

    n_steps Trotter steps; each step = Rzz(theta_J) on all 144 heavy-hex edges
    then Rx(phi) on all 127 qubits. Default theta_J=-pi/2 (max entangling),
    phi=pi/2 (the deep regime emphasised in the paper).
    """
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{N_EAGLE}];"]
    for _ in range(n_steps):
        for a, b in EAGLE_127_EDGES:
            lines.append(f"rzz({theta_J}) q[{a}],q[{b}];")
        for qi in range(N_EAGLE):
            lines.append(f"rx({phi}) q[{qi}];")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(f"Eagle-127 heavy-hex: {N_EAGLE} qubits, {N_EDGES} edges, max degree {MAX_DEGREE}")
