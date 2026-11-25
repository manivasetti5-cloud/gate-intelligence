"""Seed official 5-branch GATE syllabus hierarchies (CS, DA, EC, ME, EE)."""

from datetime import date

from app.extensions import db
from app.models.syllabus import (
    Branch,
    Chapter,
    Concept,
    Subject,
    SyllabusVersion,
    Topic,
)

GENERAL_APTITUDE_SUBJECT = {
    "code": "GA",
    "name": "General Aptitude",
    "is_general_aptitude": True,
    "weightage_percent": 15.0,
    "chapters": [
        {
            "name": "Verbal Aptitude",
            "topics": [
                ("Grammar & Usage", ["Tenses and Articles", "Prepositions and Conjunctions", "Subject-Verb Agreement"]),
                ("Vocabulary & Comprehension", ["Synonyms and Antonyms", "Reading Comprehension", "Narrative Sequencing"]),
            ],
        },
        {
            "name": "Quantitative Aptitude",
            "topics": [
                ("Data Interpretation & Numeracy", ["Bar Graphs and Pie Charts", "Ratios and Percentages", "Time, Speed and Work"]),
                ("Elementary Mathematics", ["Permutations and Probability", "Geometry and Mensuration", "Logarithms and Exponents"]),
            ],
        },
        {
            "name": "Analytical & Spatial Aptitude",
            "topics": [
                ("Logical Reasoning", ["Deduction and Induction", "Syllogisms and Analogies", "Number Series"]),
                ("Spatial Transformations", ["2D/3D Rotations and Mirroring", "Paper Folding and Cutting", "Pattern Completion"]),
            ],
        },
    ],
}

BRANCH_SYLLABI = {
    "CS": [
        {
            "code": "CS-EM",
            "name": "Engineering Mathematics",
            "weightage_percent": 13.0,
            "chapters": [
                {
                    "name": "Discrete Mathematics",
                    "topics": [
                        ("Propositional and First-Order Logic", ["Truth Tables and Equivalences", "Quantifiers and Inference Rules"]),
                        ("Sets, Relations, and Functions", ["Partial Orders and Lattices", "Equivalence Relations", "Hasse Diagrams"]),
                        ("Graph Theory", ["Connectivity and Planar Graphs", "Graph Coloring and Matching", "Euler and Hamilton Paths"]),
                        ("Combinatorics", ["Counting and Pigeonhole Principle", "Generating Functions", "Recurrence Relations"]),
                    ],
                },
                {
                    "name": "Linear Algebra",
                    "topics": [
                        ("Matrices and Determinants", ["Rank and Nullity", "System of Linear Equations"]),
                        ("Eigenvalues and Vectors", ["Diagonalization", "LU Decomposition"]),
                    ],
                },
                {
                    "name": "Calculus & Probability",
                    "topics": [
                        ("Differential and Integral Calculus", ["Limits and Continuity", "Maxima and Minima", "Mean Value Theorems"]),
                        ("Probability and Distributions", ["Bayes Theorem", "Random Variables and Expectation", "Poisson and Normal Distributions"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-DL",
            "name": "Digital Logic",
            "weightage_percent": 6.0,
            "chapters": [
                {
                    "name": "Boolean Algebra & Combinational Circuits",
                    "topics": [
                        ("Minimization", ["Karnaugh Maps", "Canonical Forms and Logic Gates"]),
                        ("Combinational Design", ["Multiplexers and Decoders", "Adders and Comparators"]),
                    ],
                },
                {
                    "name": "Sequential Circuits & Number Representation",
                    "topics": [
                        ("Flip-Flops and Counters", ["SR, JK, D, T Flip-Flops", "Synchronous and Ripple Counters", "Finite State Machines"]),
                        ("Computer Arithmetic", ["Fixed and IEEE-754 Floating Point", "Two's Complement Arithmetic"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-COA",
            "name": "Computer Organization and Architecture",
            "weightage_percent": 8.0,
            "chapters": [
                {
                    "name": "Processor & Pipelining",
                    "topics": [
                        ("Machine Instructions", ["Addressing Modes", "ALU and Control Unit Design"]),
                        ("Instruction Pipelining", ["Data, Control, and Structural Hazards", "Speedup and CPI Analysis"]),
                    ],
                },
                {
                    "name": "Memory Hierarchy & I/O",
                    "topics": [
                        ("Cache Memory", ["Direct, Associative, and Set-Associative Mapping", "Replacement Policies and AMAT"]),
                        ("I/O Interface", ["Interrupts and DMA", "Programmed I/O"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-PDS",
            "name": "Programming and Data Structures",
            "weightage_percent": 11.0,
            "chapters": [
                {
                    "name": "C Programming & Linear Structures",
                    "topics": [
                        ("Programming in C", ["Pointers and Arrays", "Recursion and Activation Records", "Scope and Storage Classes"]),
                        ("Stacks, Queues & Linked Lists", ["Infix-Postfix Conversion", "Circular Queues", "Singly and Doubly Linked Lists"]),
                    ],
                },
                {
                    "name": "Trees, Heaps & Graphs",
                    "topics": [
                        ("Trees", ["Binary Trees and Traversals", "Binary Search Trees", "AVL Tree Rotations"]),
                        ("Heaps & Graph Representation", ["Binary Max/Min Heaps", "Adjacency Matrix and List"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-ALGO",
            "name": "Algorithms",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Asymptotic Analysis & Design Paradigms",
                    "topics": [
                        ("Complexity & Searching/Sorting", ["Asymptotic Notations", "Quicksort and Mergesort", "Hashing and Collision Resolution"]),
                        ("Greedy & Dynamic Programming", ["Huffman Coding", "Matrix Chain Multiplication", "Longest Common Subsequence"]),
                    ],
                },
                {
                    "name": "Graph Algorithms",
                    "topics": [
                        ("Traversals & MST", ["BFS and DFS", "Prim's and Kruskal's Algorithms"]),
                        ("Shortest Paths", ["Dijkstra's Algorithm", "Bellman-Ford and Floyd-Warshall"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-TOC",
            "name": "Theory of Computation",
            "weightage_percent": 8.0,
            "chapters": [
                {
                    "name": "Regular & Context-Free Languages",
                    "topics": [
                        ("Finite Automata", ["DFA, NFA, and Equivalence", "Regular Expressions and Pumping Lemma", "Myhill-Nerode Theorem"]),
                        ("Pushdown Automata & CFGs", ["Ambiguity and Normal Forms", "DPDA vs NPDA", "Closure Properties"]),
                    ],
                },
                {
                    "name": "Turing Machines & Undecidability",
                    "topics": [
                        ("Computability", ["Turing Machine Variants", "Recursive and Recursively Enumerable Languages", "Halting Problem and Rice's Theorem"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-CD",
            "name": "Compiler Design",
            "weightage_percent": 5.0,
            "chapters": [
                {
                    "name": "Front-End & Parsing",
                    "topics": [
                        ("Lexical & Syntax Analysis", ["LL(1) Parsing", "SLR, LALR, and CLR Parsers", "Syntax-Directed Translation"]),
                    ],
                },
                {
                    "name": "Intermediate Code & Optimization",
                    "topics": [
                        ("Code Generation & Data Flow", ["Three-Address Code and SSA", "Runtime Environments", "Live Variable and Reaching Definitions"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-OS",
            "name": "Operating System",
            "weightage_percent": 9.0,
            "chapters": [
                {
                    "name": "Processes, Scheduling & Concurrency",
                    "topics": [
                        ("Process & Thread Management", ["System Calls and Fork", "CPU Scheduling Algorithms"]),
                        ("Synchronization & Deadlocks", ["Semaphores and Mutexes", "Classical Synchronization Problems", "Banker's Algorithm and Resource Allocation Graphs"]),
                    ],
                },
                {
                    "name": "Memory & File Systems",
                    "topics": [
                        ("Virtual Memory", ["Paging and Page Tables", "TLB and Effective Access Time", "Page Replacement Algorithms"]),
                        ("Disk & File Management", ["Inodes and Allocation", "Disk Scheduling"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-DBMS",
            "name": "Databases",
            "weightage_percent": 8.0,
            "chapters": [
                {
                    "name": "Relational Design & Querying",
                    "topics": [
                        ("ER Model & Relational Algebra", ["ER-to-Relational Mapping", "Relational Algebra and Tuple Calculus", "SQL Joins and Aggregation"]),
                        ("Normalization", ["Functional Dependencies", "1NF, 2NF, 3NF, BCNF", "Lossless Join and Dependency Preservation"]),
                    ],
                },
                {
                    "name": "Indexing & Transactions",
                    "topics": [
                        ("File Organization", ["B-Trees and B+ Trees", "Dense and Sparse Indexing"]),
                        ("Concurrency Control", ["ACID Properties", "Conflict Serializability", "Two-Phase Locking and Timestamp Ordering"]),
                    ],
                },
            ],
        },
        {
            "code": "CS-CN",
            "name": "Computer Networks",
            "weightage_percent": 7.0,
            "chapters": [
                {
                    "name": "Data Link & Network Layer",
                    "topics": [
                        ("Framing & MAC", ["CRC and Sliding Window Protocols", "CSMA/CD and Ethernet"]),
                        ("IP Addressing & Routing", ["IPv4 Subnetting and CIDR", "NAT and Fragmentation", "Distance Vector and Link State Routing"]),
                    ],
                },
                {
                    "name": "Transport & Application Layers",
                    "topics": [
                        ("TCP & UDP", ["Three-Way Handshake", "TCP Flow and Congestion Control", "UDP Header"]),
                        ("Application Protocols", ["DNS, HTTP, SMTP, and FTP"]),
                    ],
                },
            ],
        },
    ],
    "DA": [
        {
            "code": "DA-PS",
            "name": "Probability and Statistics",
            "weightage_percent": 16.0,
            "chapters": [
                {
                    "name": "Probability Foundations",
                    "topics": [
                        ("Combinatorics & Axioms", ["Permutations and Combinations", "Conditional Probability and Bayes Theorem"]),
                        ("Random Variables", ["Discrete and Continuous Distributions", "Expectation, Variance, and Covariance", "Central Limit Theorem"]),
                    ],
                },
                {
                    "name": "Statistical Inference",
                    "topics": [
                        ("Estimation & Hypothesis Testing", ["Maximum Likelihood Estimation", "Confidence Intervals", "z-test, t-test, and Chi-squared Test"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-LA",
            "name": "Linear Algebra",
            "weightage_percent": 13.0,
            "chapters": [
                {
                    "name": "Vector Spaces & Matrices",
                    "topics": [
                        ("Spaces & Linear Independence", ["Basis and Dimension", "Projection and Orthogonal Matrices"]),
                        ("Matrix Decompositions", ["Rank, Nullity, and Gaussian Elimination", "Eigenvalues and Eigenvectors", "LU and Singular Value Decomposition"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-CO",
            "name": "Calculus and Optimization",
            "weightage_percent": 9.0,
            "chapters": [
                {
                    "name": "Single-Variable Calculus & Extrema",
                    "topics": [
                        ("Differentiation & Series", ["Limits, Continuity, and Differentiability", "Taylor Series Expansion"]),
                        ("Optimization", ["Critical Points, Maxima and Minima", "Convexity and Gradient Descent Intuition"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-PDSA",
            "name": "Programming, Data Structures and Algorithms",
            "weightage_percent": 15.0,
            "chapters": [
                {
                    "name": "Python & Core Data Structures",
                    "topics": [
                        ("Python Programming", ["Functions, Iterators, and Recursion", "Time Complexity of Python Operations"]),
                        ("Linear & Tree Structures", ["Stacks, Queues, Linked Lists", "Trees and Hash Tables"]),
                    ],
                },
                {
                    "name": "Sorting & Graph Algorithms",
                    "topics": [
                        ("Search & Sort", ["Linear and Binary Search", "Selection, Bubble, Insertion Sort", "Mergesort and Quicksort"]),
                        ("Graph Algorithms", ["BFS and DFS Traversals", "Shortest Path Algorithms"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-DBW",
            "name": "Database Management and Warehousing",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Relational Databases & Indexing",
                    "topics": [
                        ("ER & Relational Models", ["Relational Algebra and Tuple Calculus", "SQL Queries"]),
                        ("Normalization & Storage", ["Normal Forms", "File Organization and Indexing"]),
                    ],
                },
                {
                    "name": "Data Warehousing",
                    "topics": [
                        ("Data Transformation & Schemas", ["Normalization, Discretization, and Sampling", "Star and Snowflake Multidimensional Schemas"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-ML",
            "name": "Machine Learning",
            "weightage_percent": 12.0,
            "chapters": [
                {
                    "name": "Supervised Learning",
                    "topics": [
                        ("Regression & Classification", ["Simple, Multiple, and Ridge Regression", "Logistic Regression and Naive Bayes", "k-NN, LDA, SVM, and Decision Trees"]),
                        ("Model Evaluation & Neural Nets", ["Bias-Variance Tradeoff", "Cross-Validation", "Multi-Layer Perceptron"]),
                    ],
                },
                {
                    "name": "Unsupervised Learning",
                    "topics": [
                        ("Clustering & Dimensionality Reduction", ["k-Means and k-Medoids", "Hierarchical Clustering", "Principal Component Analysis"]),
                    ],
                },
            ],
        },
        {
            "code": "DA-AI",
            "name": "Artificial Intelligence",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Search & Logic",
                    "topics": [
                        ("State-Space Search", ["Uninformed Search (BFS/DFS/UCS)", "Informed Search (A* and Heuristics)", "Adversarial Search and Alpha-Beta Pruning"]),
                        ("Knowledge Representation", ["Propositional Logic", "First-Order Predicate Logic"]),
                    ],
                },
                {
                    "name": "Reasoning Under Uncertainty",
                    "topics": [
                        ("Probabilistic Graphical Models", ["Conditional Independence & Bayesian Networks", "Variable Elimination and Sampling"]),
                    ],
                },
            ],
        },
    ],
    "EC": [
        {
            "code": "EC-EM",
            "name": "Engineering Mathematics",
            "weightage_percent": 13.0,
            "chapters": [
                {
                    "name": "Linear Algebra, Calculus & Differential Equations",
                    "topics": [
                        ("Matrices & Vector Calculus", ["Eigenvalues and Vector Spaces", "Gradient, Divergence, Curl, Stokes/Gauss Theorems"]),
                        ("ODEs, Complex Analysis & Probability", ["First and Higher Order ODEs", "Cauchy Integral Theorem and Residues", "Random Variables and Distributions"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-NS",
            "name": "Networks, Signals and Systems",
            "weightage_percent": 15.0,
            "chapters": [
                {
                    "name": "Network Analysis",
                    "topics": [
                        ("Circuit Theorems & Steady State", ["Node/Mesh, Thevenin/Norton, Superposition", "Sinusoidal Steady State & Resonance", "Two-Port Networks and Transient Response"]),
                    ],
                },
                {
                    "name": "Signals & Systems",
                    "topics": [
                        ("LTI Systems & Transforms", ["Continuous/Discrete Convolution", "Fourier Series and Fourier Transform", "Laplace, Z-Transform, and Sampling Theorem"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-ED",
            "name": "Electronic Devices",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Semiconductor Physics & Junctions",
                    "topics": [
                        ("Carrier Transport", ["Energy Bands and Fermi Level", "Drift, Diffusion, Continuity Equation"]),
                        ("Diodes, BJT & MOSFET", ["P-N Junction and Zener Diode", "BJT Physics", "MOS Capacitor and MOSFET Characteristics"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-AC",
            "name": "Analog Circuits",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Diode & Transistor Amplifiers",
                    "topics": [
                        ("Diode & Small-Signal Circuits", ["Clippers, Clampers, and Rectifiers", "BJT and MOSFET Amplifiers", "Frequency Response and Feedback"]),
                    ],
                },
                {
                    "name": "Op-Amp Circuits & Oscillators",
                    "topics": [
                        ("Operational Amplifiers", ["Inverting/Non-Inverting/Integrator/Differentiator", "Active Filters and Oscillators", "555 Timer Circuits"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-DC",
            "name": "Digital Circuits",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Combinational & Sequential Logic",
                    "topics": [
                        ("Logic Design", ["Boolean Minimization and K-Maps", "Mux, Decoders, and Arithmetic Circuits", "Flip-Flops, Counters, and FSMs"]),
                        ("Converters & Memory", ["ADC and DAC Architectures", "Semiconductor Memories and Timing"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-CS",
            "name": "Control Systems",
            "weightage_percent": 9.0,
            "chapters": [
                {
                    "name": "Time & Frequency Domain Analysis",
                    "topics": [
                        ("Modeling & Stability", ["Block Diagrams and Signal Flow Graphs", "Routh-Hurwitz Criterion", "Root Locus, Bode, and Nyquist Plots"]),
                        ("State Space & Compensation", ["Lead-Lag Compensators", "State Transition Matrix and Controllability"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-COM",
            "name": "Communications",
            "weightage_percent": 10.0,
            "chapters": [
                {
                    "name": "Analog & Digital Communications",
                    "topics": [
                        ("Random Processes & Analog Mod", ["Autocorrelation and PSD", "AM, FM, and Superheterodyne Receivers"]),
                        ("Digital Mod & Information Theory", ["PCM, ASK, PSK, QAM, Matched Filter, BER", "Entropy, Channel Capacity, and Error Control Coding"]),
                    ],
                },
            ],
        },
        {
            "code": "EC-EMT",
            "name": "Electromagnetics",
            "weightage_percent": 8.0,
            "chapters": [
                {
                    "name": "Waves, Transmission Lines & Antennas",
                    "topics": [
                        ("Maxwell Equations & Waveguides", ["Plane Wave Propagation", "Transmission Lines and Smith Chart", "Rectangular Waveguides and Optical Fibers"]),
                        ("Antennas", ["Dipole Antennas, Arrays, and Radiation Pattern"]),
                    ],
                },
            ],
        },
    ],
    "ME": [
        {
            "code": "ME-EM",
            "name": "Engineering Mathematics",
            "weightage_percent": 13.0,
            "chapters": [
                {
                    "name": "Mathematics for Mechanical Engineering",
                    "topics": [
                        ("Linear Algebra & Calculus", ["Matrices and Eigenvalues", "Partial Derivatives and Multiple Integrals"]),
                        ("Differential Equations, Probability & Numerical", ["ODEs and PDEs (Heat/Wave/Laplace)", "Probability Distributions", "Newton-Raphson, Trapezoidal, and Simpson Rules"]),
                    ],
                },
            ],
        },
        {
            "code": "ME-AMD",
            "name": "Applied Mechanics and Design",
            "weightage_percent": 28.0,
            "chapters": [
                {
                    "name": "Engineering Mechanics & Strength of Materials",
                    "topics": [
                        ("Statics & Dynamics", ["Free-Body Diagrams and Trusses", "Friction and Kinematics/Kinetics"]),
                        ("Mechanics of Materials", ["Stress-Strain and Mohr's Circle", "SFD/BMD and Bending Stresses", "Torsion and Euler Buckling"]),
                    ],
                },
                {
                    "name": "Theory of Machines & Machine Design",
                    "topics": [
                        ("Mechanisms & Vibrations", ["Planar Mechanisms and Gears", "Flywheels and Free/Forced Vibrations"]),
                        ("Machine Elements", ["Static and Fatigue Failure Theories", "Shafts, Bearings, Joints, and Brakes"]),
                    ],
                },
            ],
        },
        {
            "code": "ME-FMT",
            "name": "Fluid Mechanics and Thermal Sciences",
            "weightage_percent": 26.0,
            "chapters": [
                {
                    "name": "Fluid Mechanics & Heat Transfer",
                    "topics": [
                        ("Fluid Statics & Dynamics", ["Manometry and Buoyancy", "Bernoulli Equation and Pipe Flow", "Boundary Layer and Compressible Flow"]),
                        ("Heat Transfer", ["1D Steady Conduction and Fins", "Convection Correlations and Radiation", "LMTD and NTU Heat Exchangers"]),
                    ],
                },
                {
                    "name": "Thermodynamics & Applications",
                    "topics": [
                        ("Laws of Thermodynamics", ["First Law for Closed/Open Systems", "Second Law, Entropy, and Availability"]),
                        ("Power & Refrigeration Cycles", ["Rankine, Otto, Diesel, and Brayton Cycles", "Vapor Compression Refrigeration and Psychrometrics"]),
                    ],
                },
            ],
        },
        {
            "code": "ME-MMI",
            "name": "Materials, Manufacturing and Industrial Engineering",
            "weightage_percent": 18.0,
            "chapters": [
                {
                    "name": "Engineering Materials & Manufacturing",
                    "topics": [
                        ("Materials & Heat Treatment", ["Iron-Carbon Diagram and TTT Curves", "Ferrous and Non-Ferrous Alloys"]),
                        ("Casting, Forming, Joining & Machining", ["Gating and Solidification", "Rolling, Forging, Extrusion, Welding", "Merchant Circle, Tool Life, and CNC"]),
                    ],
                },
                {
                    "name": "Metrology & Industrial Engineering",
                    "topics": [
                        ("Metrology & Operations Research", ["Limits, Fits, and Tolerances", "Inventory Control (EOQ) and Scheduling", "Linear Programming, PERT/CPM, and Queuing"]),
                    ],
                },
            ],
        },
    ],
    "EE": [
        {
            "code": "EE-EM",
            "name": "Engineering Mathematics",
            "weightage_percent": 13.0,
            "chapters": [
                {
                    "name": "Core Engineering Mathematics",
                    "topics": [
                        ("Linear Algebra, Calculus & Vector Analysis", ["Matrix Theory and Eigenvalues", "Line, Surface, and Volume Integrals"]),
                        ("Differential Equations, Complex & Numerical", ["ODEs and Laplace/Fourier Transforms", "Complex Residues and Probability", "Numerical Integration and Root Finding"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-EC",
            "name": "Electric Circuits",
            "weightage_percent": 12.0,
            "chapters": [
                {
                    "name": "Network Theorems, AC & Transients",
                    "topics": [
                        ("DC & AC Networks", ["KCL/KVL, Node & Mesh Analysis", "Thevenin, Norton, Maximum Power Transfer", "Three-Phase Balanced/Unbalanced Circuits"]),
                        ("Transients & Two-Port", ["RL, RC, RLC Transient Analysis", "Z, Y, ABCD, h Parameters and Resonance"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-EMF",
            "name": "Electromagnetic Fields",
            "weightage_percent": 5.0,
            "chapters": [
                {
                    "name": "Electrostatics & Magnetostatics",
                    "topics": [
                        ("Field Laws & Inductance", ["Gauss's Law and Capacitance", "Biot-Savart, Ampere's Law, and Faraday's Law", "Self and Mutual Inductance"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-SS",
            "name": "Signals and Systems",
            "weightage_percent": 7.0,
            "chapters": [
                {
                    "name": "Transforms & LTI Systems",
                    "topics": [
                        ("Continuous & Discrete Systems", ["Convolution and LTI Properties", "Fourier, Laplace, Z-Transforms, and Sampling"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-EMAC",
            "name": "Electrical Machines",
            "weightage_percent": 12.0,
            "chapters": [
                {
                    "name": "Transformers & Rotating Machines",
                    "topics": [
                        ("Transformers & DC Machines", ["Equivalent Circuit, Efficiency, Regulation", "DC Generators and Motors Speed Control"]),
                        ("AC Machines", ["3-Phase Induction Motor Torque-Slip", "1-Phase Induction & Synchronous Machines"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-PS",
            "name": "Power Systems",
            "weightage_percent": 12.0,
            "chapters": [
                {
                    "name": "Transmission, Load Flow & Faults",
                    "topics": [
                        ("Lines & Per-Unit Systems", ["ABCD Parameters and Ferranti Effect", "Y-bus, Gauss-Seidel, and Newton-Raphson Load Flow"]),
                        ("Faults, Protection & Stability", ["Symmetrical Components and Fault Analysis", "Relays, Circuit Breakers, and Equal Area Criterion"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-CS",
            "name": "Control Systems",
            "weightage_percent": 8.0,
            "chapters": [
                {
                    "name": "Classical & State-Space Control",
                    "topics": [
                        ("Stability & Compensators", ["Routh-Hurwitz, Root Locus, Bode, Nyquist", "PID, Lead-Lag Controllers, and State-Space"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-MEAS",
            "name": "Electrical and Electronic Measurements",
            "weightage_percent": 5.0,
            "chapters": [
                {
                    "name": "Bridges, Instruments & Errors",
                    "topics": [
                        ("Measurement Systems", ["AC/DC Bridges and Wattmeters", "CT/PT, Digital Voltmeters, Oscilloscopes, and Error Analysis"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-ADE",
            "name": "Analog and Digital Electronics",
            "weightage_percent": 5.0,
            "chapters": [
                {
                    "name": "Op-Amps & Digital Logic",
                    "topics": [
                        ("Analog & Digital Circuits", ["Diode/BJT/MOSFET & Op-Amp Circuits", "Combinational/Sequential Logic, Mux, ADC/DAC"]),
                    ],
                },
            ],
        },
        {
            "code": "EE-PE",
            "name": "Power Electronics",
            "weightage_percent": 6.0,
            "chapters": [
                {
                    "name": "Converters & Inverters",
                    "topics": [
                        ("Switches & Rectifiers", ["SCR, MOSFET, IGBT Characteristics", "Single and Three-Phase Controlled Rectifiers"]),
                        ("Choppers & Inverters", ["Buck, Boost, Buck-Boost DC-DC Converters", "Single/Three-Phase PWM Inverters"]),
                    ],
                },
            ],
        },
    ],
}


def _populate_subject(syllabus_version_id: int, subj_dict: dict, order: int) -> None:
    subject = Subject(
        syllabus_version_id=syllabus_version_id,
        code=subj_dict["code"],
        name=subj_dict["name"],
        display_order=order,
        weightage_percent=subj_dict.get("weightage_percent"),
        is_general_aptitude=subj_dict.get("is_general_aptitude", False),
        status="active",
    )
    db.session.add(subject)
    db.session.flush()

    for ch_idx, ch_dict in enumerate(subj_dict.get("chapters", []), start=1):
        chapter = Chapter(
            subject_id=subject.id,
            name=ch_dict["name"],
            display_order=ch_idx,
            is_outdated_in_latest=False,
        )
        db.session.add(chapter)
        db.session.flush()

        for tp_idx, (tp_name, concepts) in enumerate(ch_dict.get("topics", []), start=1):
            topic = Topic(
                chapter_id=chapter.id,
                name=tp_name,
                display_order=tp_idx,
                is_outdated_in_latest=False,
            )
            db.session.add(topic)
            db.session.flush()

            for cp_idx, cp_name in enumerate(concepts, start=1):
                concept = Concept(
                    topic_id=topic.id,
                    name=cp_name,
                    display_order=cp_idx,
                    is_outdated_in_latest=False,
                )
                db.session.add(concept)


def seed_syllabus() -> int:
    """Idempotently seed official syllabus versions for all 5 GATE branches."""
    versions_created = 0
    branches = Branch.query.all()
    for branch in branches:
        if branch.code not in BRANCH_SYLLABI:
            continue
        target_years = [2026, 2025] if branch.code == "DA" else [2026, 2025, 2024]
        for year in target_years:
            existing = SyllabusVersion.query.filter_by(
                branch_id=branch.id, exam_year=year, version_label="Official v1.0"
            ).first()
            if existing:
                continue

            sv = SyllabusVersion(
                branch_id=branch.id,
                exam_year=year,
                version_label="Official v1.0",
                syllabus_source=f"Official GATE {year} Organizing Institute Syllabus ({branch.code})",
                effective_date=date(year - 1, 8, 1),
                status="active",
                notes=f"Official syllabus hierarchy for GATE {year} {branch.code}.",
            )
            db.session.add(sv)
            db.session.flush()

            _populate_subject(sv.id, GENERAL_APTITUDE_SUBJECT, order=1)
            for idx, subj in enumerate(BRANCH_SYLLABI[branch.code], start=2):
                _populate_subject(sv.id, subj, order=idx)

            versions_created += 1

    db.session.commit()
    return versions_created


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        count = seed_syllabus()
        print(f"Seeded {count} syllabus versions.")
