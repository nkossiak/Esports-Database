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
    EdgeType TEXT NOT NULL, -- 'Plays_For', 'Played_In', 'Won_By', etc.
    Metadata JSON,
    FOREIGN KEY (SourceNodeID) REFERENCES Nodes(NodeID),
    FOREIGN KEY (TargetNodeID) REFERENCES Nodes(NodeID)
);

CREATE TABLE Graphs (
    GraphID INTEGER PRIMARY KEY,
    GraphName TEXT NOT NULL UNIQUE,
    Description TEXT
);

CREATE TABLE GraphMemberships (
    MembershipID INTEGER PRIMARY KEY AUTOINCREMENT,
    GraphID INTEGER NOT NULL,
    NodeID INTEGER,
    EdgeID INTEGER,
    FOREIGN KEY (GraphID) REFERENCES Graphs(GraphID),
    FOREIGN KEY (NodeID) REFERENCES Nodes(NodeID),
    FOREIGN KEY (EdgeID) REFERENCES Edges(EdgeID),
    CHECK (NodeID IS NOT NULL OR EdgeID IS NOT NULL)
);

CREATE UNIQUE INDEX idx_graph_node_unique
    ON GraphMemberships (GraphID, NodeID)
    WHERE NodeID IS NOT NULL;

CREATE UNIQUE INDEX idx_graph_edge_unique
    ON GraphMemberships (GraphID, EdgeID)
    WHERE EdgeID IS NOT NULL;
