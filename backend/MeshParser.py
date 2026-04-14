import xml.etree.ElementTree as ET
from pathlib import Path
import logging

log = logging.getLogger(__name__)


class MeshParser:
    def __init__(self, mesh_file_path: str = "desc2026.xml"):
        self.mesh_file_path = mesh_file_path
        self.tree_to_term = {}
        self.term_to_tree = {}
        self._load_mesh()

    def _load_mesh(self):
        """Įkelia MeSH XML failą"""
        if not Path(self.mesh_file_path).exists():
            raise FileNotFoundError(f"MeSH file not found: {self.mesh_file_path}")

        try:
            tree = ET.parse(self.mesh_file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            log.error(f"XML parsing error: {e}")
            raise

        # Ieškome DescriptorRecord elementų
        descriptors = root.findall('.//DescriptorRecord')

        if not descriptors:
            log.warning("No DescriptorRecord elements found")
            return

        log.info(f"Found {len(descriptors)} DescriptorRecord elements")

        count = 0
        for descriptor in descriptors:
            term_text = self._extract_term_text(descriptor)
            if not term_text:
                continue

            tree_numbers = self._extract_tree_numbers(descriptor)
            for tn in tree_numbers:
                self.tree_to_term[tn] = term_text
                self.term_to_tree.setdefault(term_text, []).append(tn)
                count += 1

        log.info(f"Loaded {count} tree number → term mappings")

    def _extract_term_text(self, descriptor) -> str | None:
        """Ištraukia termino tekstą iš DescriptorRecord"""
        term_elem = descriptor.find('.//DescriptorName')
        if term_elem is None:
            return None

        string_elem = term_elem.find('.//String')
        if string_elem is None:
            return None

        return string_elem.text

    def _extract_tree_numbers(self, descriptor) -> list[str]:
        """Ištraukia tree numbers iš DescriptorRecord"""
        tree_numbers = descriptor.findall('.//TreeNumber')
        return [tn.text for tn in tree_numbers if tn.text]

    def get_descendants(self, tree_number: str, levels: int = 2) -> list[str]:
        """Grąžina sub-terminus iki nurodyto gylio"""
        results = []

        # Pridedame patį terminą
        root_term = self.tree_to_term.get(tree_number)
        if root_term:
            results.append(root_term)

        # Ieškome palikuonių
        for tn, term in self.tree_to_term.items():
            if tn.startswith(tree_number + "."):
                depth = tn.count(".") - tree_number.count(".")
                if depth <= levels:
                    results.append(term)

        # Pašaliname dublikatus išlaikant tvarką
        seen = set()
        return [term for term in results if term not in seen and not seen.add(term)]

    def get_descriptor(self, tree_number: str) -> str | None:
        """Grąžina termino pavadinimą pagal tree number"""
        return self.tree_to_term.get(tree_number)

    def get_tree_numbers(self, term: str) -> list[str]:
        """Grąžina tree numbers pagal terminą"""
        return self.term_to_tree.get(term, [])

    def get_all_roots(self) -> list[str]:
        """Grąžina visus šakninius tree numbers (vieno simbolio)"""
        roots = {tn for tn in self.tree_to_term.keys()
                 if len(tn) == 3 and tn[1:].isdigit()}
        return sorted(roots)


def get_optimal_topics() -> list[str]:

    ROOT_TREES = [
        "C04", "C06", "C08", "C10", "C14", "C18", "C19", "C20", "F03", "G01", "G02"
    ]

    try:
        m = MeshParser()
        topics = []

        for root in ROOT_TREES:
            descendants = m.get_descendants(root, levels=2)
            print(f"  {root}: {len(descendants)} terms")
            topics.extend(descendants)

        # Pašaliname dublikatus ir filtruojame
        topics = list(set(topics))
        original_count = len(topics)
        topics = [t for t in topics if len(t.split()) <= 6]

        print(f"\nGenerated {len(topics)} topics (from {original_count})")

        print("\nExample topics:")
        for topic in topics[:20]:
            print(f"  - {topic}")

        return topics

    except FileNotFoundError:
        log.error("MeSH file not found")
        return ROOT_TREES
    except Exception as e:
        log.error(f"Error generating topics: {e}")
        return ROOT_TREES