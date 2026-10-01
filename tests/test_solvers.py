from certhub.solvers.ocr_solver import OCRSolver


def test_ocr_solver_instancia():
    solver = OCRSolver()
    assert solver.threshold == 0.7


def test_math_solver(monkeypatch):
    solver = OCRSolver()
    monkeypatch.setattr(solver, "resolver", lambda _x: "7 + 3")
    assert solver.resolver_matematico(b"fake") == "10"
