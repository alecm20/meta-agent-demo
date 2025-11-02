import unittest
from app.services.tools import CalculatorTool, ToolExecutionError


class CalculatorToolTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_addition(self) -> None:
        tool = CalculatorTool()
        result = await tool.run("1 + 2 + 3")
        self.assertEqual(result, "6.0")

    async def test_invalid_expression(self) -> None:
        tool = CalculatorTool()
        with self.assertRaises(ToolExecutionError):
            await tool.run("1 ++ 2")


if __name__ == "__main__":
    unittest.main()
