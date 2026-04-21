DROP TABLE IF EXISTS GraphMemberships;
DROP TABLE IF EXISTS Graphs;
DROP TABLE IF EXISTS Edges;
DROP TABLE IF EXISTS Nodes;

CREATE TABLE Nodes (
    NodeID INTEGER PRIMARY KEY AUTOINCREMENT,
    NodeType TEXT NOT NULL, -- 'Player', 'Team', 'Tournament'
    Name TEXT NOT NULL,
    Attributes JSON         -- Flexible metadata
);

CREATE TABLE Edges (
    EdgeID INTEGER PRIMARY KEY AUTOINCREMENT,
    SourceNodeID INTEGER NOT NULL,
    TargetNodeID INTEGER NOT NULL,
    EdgeType TEXT NOT NULL, -- 'Plays_For', 'Played_In', etc.
    Metadata JSON,
    FOREIGN KEY (SourceNodeID) REFERENCES Nodes(NodeID),
    FOREIGN KEY (TargetNodeID) REFERENCES Nodes(NodeID)
);