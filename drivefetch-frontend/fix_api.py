with open('src/utils/api.ts', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("import { Car, ChatMessage, CalculatorResult, CarEvaluation } from '../types';", "import { Car, ChatMessage, CarEvaluation } from '../types';")
content = content.replace("signal: signal,", "signal: signal || undefined,")

with open('src/utils/api.ts', 'w', encoding='utf-8') as f:
    f.write(content)
