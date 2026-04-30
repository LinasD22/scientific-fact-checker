import xml.etree.ElementTree as ET
from pathlib import Path
import logging

log = logging.getLogger(__name__)


class MeshParser:
    # https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/
    def __init__(self, mesh_file_path: str = "desc2026.xml"):
        self.mesh_file_path = mesh_file_path
        self.tree_to_term = {}
        self.term_to_tree = {}
        self._load_mesh()

    def _load_mesh(self):
        if not Path(self.mesh_file_path).exists():
            raise FileNotFoundError(f"MeSH file not found: {self.mesh_file_path}")

        try:
            tree = ET.parse(self.mesh_file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            log.error(f"XML parsing error: {e}")
            raise

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
            for tn in self._extract_tree_numbers(descriptor):
                self.tree_to_term[tn] = term_text
                self.term_to_tree.setdefault(term_text, []).append(tn)
                count += 1

        log.info(f"Loaded {count} tree number → term mappings")

    def _extract_term_text(self, descriptor) -> str | None:
        term_elem = descriptor.find('.//DescriptorName')
        if term_elem is None:
            return None
        string_elem = term_elem.find('.//String')
        return string_elem.text if string_elem is not None else None

    def _extract_tree_numbers(self, descriptor) -> list[str]:
        return [tn.text for tn in descriptor.findall('.//TreeNumber') if tn.text]

    def get_descendants(self, tree_number: str, levels: int = 3) -> list[str]:
        results = []
        root_term = self.tree_to_term.get(tree_number)
        if root_term:
            results.append(root_term)
        for tn, term in self.tree_to_term.items():
            if tn.startswith(tree_number + "."):
                depth = tn.count(".") - tree_number.count(".")
                if depth <= levels:
                    results.append(term)
        seen = set()
        return [t for t in results if t not in seen and not seen.add(t)]

    def get_descriptor(self, tree_number: str) -> str | None:
        return self.tree_to_term.get(tree_number)

    def get_tree_numbers(self, term: str) -> list[str]:
        return self.term_to_tree.get(term, [])

    def get_all_roots(self) -> list[str]:
        roots = {tn for tn in self.tree_to_term if len(tn) == 3 and tn[1:].isdigit()}
        return sorted(roots)


def get_optimal_topics() -> list[str]:
    """
    Returns MeSH terms covering all human-relevant health topics:
    diseases, drugs, food, physiology, mental health, public health.

    Tree structure reference:
      C   Diseases (C01–C23)
      D   Chemicals and Drugs
      F   Psychiatry and Psychology
      G   Biological Phenomena / Physiology
      J   Technology, Industry, Agriculture (J02 = Food)
      N   Health Care
    """
    ROOT_TREES = [
        # ── All disease categories (C01–C23) ───────────────────────────────
        "C01",   # Bacterial Infections and Mycoses
        "C02",   # Virus Diseases (COVID, flu, hepatitis, HIV ...)
        "C03",   # Parasitic Diseases
        "C04",   # Neoplasms (cancer)
        "C05",   # Musculoskeletal Diseases (arthritis, osteoporosis ...)
        "C06",   # Digestive System Diseases
        "C07",   # Stomatognathic Diseases (dental / oral)
        "C08",   # Respiratory Tract Diseases (asthma, COPD ...)
        "C09",   # Otorhinolaryngologic Diseases (ENT)
        "C10",   # Nervous System Diseases (stroke, Alzheimer's ...)
        "C11",   # Eye Diseases
        "C12",   # Urological and Male Genital Diseases
        "C13",   # Female Urogenital Diseases and Pregnancy
        "C14",   # Cardiovascular Diseases
        "C15",   # Hemic and Lymphatic Diseases (anaemia, clotting ...)
        "C16",   # Congenital, Hereditary, Neonatal Diseases
        "C17",   # Skin and Connective Tissue Diseases
        "C18",   # Nutritional and Metabolic Diseases (diabetes, obesity ...)
        "C19",   # Endocrine System Diseases (thyroid, adrenal ...)
        "C20",   # Immune System Diseases (allergies, autoimmune ...)
        "C23",   # Pathological Conditions, Signs and Symptoms (pain, fever ...)

        # ── Drugs and chemicals ────────────────────────────────────────────
        # (D-tree covers every drug, supplement, vitamin, food chemical)
        "D02",   # Organic Chemicals (includes many pharmaceuticals)
        "D03",   # Heterocyclic Compounds (antibiotics, antivirals ...)
        "D04",   # Polycyclic Compounds (steroids, statins ...)
        "D05",   # Macromolecular Substances (proteins, polymers ...)
        "D06",   # Hormones, Hormone Substitutes, Hormone Antagonists
        "D09",   # Carbohydrates (sugars, fibre ...)
        "D10",   # Lipids (fatty acids, cholesterol ...)
        "D12",   # Amino Acids, Peptides, and Proteins
        "D20",   # Complex Mixtures (herbal extracts, plant medicines ...)
        "D26",   # Pharmaceutical Preparations (drug formulations)
        "D27",   # Chemical Actions and Uses (mechanisms of action)

        # ── Food and Beverages ─────────────────────────────────────────────
        "J02",   # Food and Beverages (every food category, dietary patterns)

        # ── Physiology and Biological Phenomena ────────────────────────────
        "G06",   # Biochemical Phenomena (metabolism, enzymes ...)
        "G07",   # Physiological Phenomena (nutrition physiology, ageing ...)
        "G08",   # Nervous System Physiological Phenomena
        "G09",   # Circulatory and Respiratory Physiology
        "G10",   # Digestive System and Oral Physiological Phenomena
        "G11",   # Musculoskeletal and Neural Physiology (exercise science)

        # ── Mental health ──────────────────────────────────────────────────
        "F01",   # Behavior and Behavior Mechanisms (addiction, cognition ...)
        "F03",   # Mental Disorders (depression, anxiety, PTSD ...)

        # ── Public health ──────────────────────────────────────────────────
        "N01",   # Population Characteristics (demographics, risk factors)
        "N06",   # Environment and Public Health (epidemiology, prevention)
    ]

    try:
        m = MeshParser()
        topics: list[str] = []

        for root in ROOT_TREES:
            # Level 3 gives specific terms (e.g. "Coronary Artery Disease")
            # rather than overly broad ones (e.g. "Heart Diseases").
            # Level 4 is available for even finer granularity if needed.
            descendants = m.get_descendants(root, levels=3)
            log.info(f"  {root}: {len(descendants)} terms")
            topics.extend(descendants)

        # Deduplicate while preserving order
        seen: set[str] = set()
        topics = [t for t in topics if t not in seen and not seen.add(t)]

        # Drop single-word terms (too broad) and very long phrases (too narrow for a query)
        topics = [t for t in topics if 2 <= len(t.split()) <= 6]

        log.info(f"Generated {len(topics)} topics")
        log.info("Example topics (first 20):")
        for t in topics[:20]:
            log.info(f"  - {t}")

        return topics

    except FileNotFoundError:
        log.error("MeSH file not found — returning empty list")
        return []
    except Exception as e:
        log.error(f"Error generating topics: {e}")
        return []