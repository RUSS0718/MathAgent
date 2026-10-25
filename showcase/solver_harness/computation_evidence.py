"""Conservative reads of computation receipts without rewriting stored history."""


def has_computation_output(receipt):
    """Require observable output; zero, false and empty structured sets are valid.

    Legacy receipts must carry the output itself. An artifact reference or an
    exit code alone cannot establish that a numerical result was produced.
    """
    output = receipt.get("output")
    if receipt.get("output_available") is False or output is None:
        return False
    if receipt.get("tool") == "python_math":
        return isinstance(output, str) and bool(output.strip())
    return True
