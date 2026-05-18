The purpose of this project is to develop an app to solve pips puzzles from the new york times website. 

These puzzles are a form of constrained optimisation problem.

There are irregularly shaped boards.

Areas of the boards have various conditions. 

There are a finite number of dominos. 
Each domino has two values on it. 

The number of squares on the boards should be twice the number of dominos. 


A key challenge with this problem for llms is interpreting the images, so understanding the constraints at play. 

A second challenge is that LLMs may not be best suited to directly solving the optimisation problem. Instead consider building an energy model which assigns energy levels to proposed domino placements based on the degree of wrongness/distance to solution. 

I will put screenshots with some examples in the examples folder. 

Create a public repo for this and save progress periodically. 

Take image parsing as the first, and possibly main challenge. 