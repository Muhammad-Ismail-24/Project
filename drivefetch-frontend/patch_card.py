with open('src/components/CarResultCard.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

import_statement = "import { evaluateSingleCar } from '../utils/api';\nimport { Car } from '../types';"
content = content.replace("import { evaluateSingleCar } from '../utils/api';", import_statement)

interface_def = """
interface Tag {
  text: string;
  type: 'danger' | 'warning' | 'positive';
}

const generateHeuristicTags = (title: string = ''): Tag[] => {
"""
content = content.replace("const generateHeuristicTags = (title = '') => {", interface_def)

props_def = """
interface Props {
  car: Car | any;
  isHighlighted?: boolean;
  savedListingIds?: Set<string>;
  onUnsave?: (id: string) => void;
  userQuery?: string;
}

export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }: Props) {
"""
content = content.replace("export default function CarResultCard({ car, isHighlighted = false, savedListingIds = new Set(), onUnsave, userQuery = '' }) {", props_def)

with open('src/components/CarResultCard.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
