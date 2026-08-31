"""Harbor coding tasks for MWGym crossover experiment.

Real Python coding tasks with deterministic verification.
Each task has: instruction, test code, expected output.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodingTask:
    """A Harbor coding task."""
    id: str
    name: str
    instruction: str
    test_code: str
    expected_output: str
    difficulty: str = "easy"  # easy, medium, hard
    tokens_estimate: int = 200


TASKS = [
    CodingTask(
        id="code-01",
        name="Hello World Function",
        instruction="Write a Python function `hello()` that returns the string 'Hello, World!'",
        test_code="assert hello() == 'Hello, World!'",
        expected_output="Hello, World!",
        difficulty="easy",
        tokens_estimate=100,
    ),
    CodingTask(
        id="code-02",
        name="Factorial",
        instruction="Write a Python function `factorial(n)` that computes n! recursively.",
        test_code="assert factorial(5) == 120; assert factorial(0) == 1; assert factorial(1) == 1",
        expected_output="120",
        difficulty="easy",
        tokens_estimate=150,
    ),
    CodingTask(
        id="code-03",
        name="FizzBuzz",
        instruction="Write a Python function `fizzbuzz(n)` that returns a list of strings from 1 to n. For multiples of 3 use 'Fizz', for 5 use 'Buzz', for both use 'FizzBuzz', otherwise the number as string.",
        test_code="assert fizzbuzz(15)[:15] == ['1','2','Fizz','4','Buzz','Fizz','7','8','Fizz','Buzz','11','Fizz','13','14','FizzBuzz']",
        expected_output="['1', '2', 'Fizz', '4', 'Buzz']",
        difficulty="easy",
        tokens_estimate=200,
    ),
    CodingTask(
        id="code-04",
        name="List Comprehension",
        instruction="Write a Python function `evens(numbers)` that returns a list of even numbers from the input list using list comprehension.",
        test_code="assert evens([1,2,3,4,5,6]) == [2,4,6]; assert evens([]) == []",
        expected_output="[2, 4, 6]",
        difficulty="easy",
        tokens_estimate=100,
    ),
    CodingTask(
        id="code-05",
        name="String Reverse",
        instruction="Write a Python function `reverse_string(s)` that reverses a string.",
        test_code="assert reverse_string('hello') == 'olleh'; assert reverse_string('') == ''",
        expected_output="olleh",
        difficulty="easy",
        tokens_estimate=100,
    ),
    CodingTask(
        id="code-06",
        name="Binary Search",
        instruction="Write a Python function `binary_search(arr, target)` that returns the index of target in sorted arr, or -1 if not found.",
        test_code="assert binary_search([1,2,3,4,5], 3) == 2; assert binary_search([1,2,3,4,5], 6) == -1",
        expected_output="2",
        difficulty="medium",
        tokens_estimate=300,
    ),
    CodingTask(
        id="code-07",
        name="Merge Sorted Lists",
        instruction="Write a Python function `merge_sorted(a, b)` that merges two sorted lists into one sorted list.",
        test_code="assert merge_sorted([1,3,5], [2,4,6]) == [1,2,3,4,5,6]; assert merge_sorted([], [1,2]) == [1,2]",
        expected_output="[1, 2, 3, 4, 5, 6]",
        difficulty="medium",
        tokens_estimate=250,
    ),
    CodingTask(
        id="code-08",
        name="Prime Check",
        instruction="Write a Python function `is_prime(n)` that returns True if n is a prime number.",
        test_code="assert is_prime(2) == True; assert is_prime(4) == False; assert is_prime(17) == True; assert is_prime(1) == False",
        expected_output="True",
        difficulty="medium",
        tokens_estimate=200,
    ),
    CodingTask(
        id="code-09",
        name="Matrix Transpose",
        instruction="Write a Python function `transpose(matrix)` that transposes a 2D list (list of lists).",
        test_code="assert transpose([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]",
        expected_output="[[1, 4], [2, 5], [3, 6]]",
        difficulty="medium",
        tokens_estimate=200,
    ),
    CodingTask(
        id="code-10",
        name="Debounce Decorator",
        instruction="Write a Python decorator `debounce(seconds)` that delays function execution until `seconds` have passed since the last call. For this test, just implement a version that records calls with timestamps.",
        test_code="""
call_log = []
@debounce(0.1)
def my_func(x):
    call_log.append(x)

my_func(1)
my_func(2)
my_func(3)
import time; time.sleep(0.2)
assert len(call_log) == 1  # only last call executed
assert call_log[0] == 3
""",
        expected_output="True",
        difficulty="hard",
        tokens_estimate=400,
    ),
]


def get_tasks(n: int = 10) -> list[CodingTask]:
    """Get first n tasks."""
    return TASKS[:n]


def get_task(task_id: str) -> CodingTask | None:
    """Get task by ID."""
    for t in TASKS:
        if t.id == task_id:
            return t
    return None
