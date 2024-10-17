import glob
from io import BytesIO
from operator import attrgetter, itemgetter
from pathlib import Path
from typing import List, Tuple, Dict
from lxml import etree


class Page:
    _TEXT_REGION = "TextRegion"

    def __init__(self, file: str, line_height=50):
        self.file = file
        self.line_height = line_height
        tree = etree.parse(file)
        root = tree.getroot()

        # Parse reading order
        self.reading_order = self.parse_reading_order(root)

        tr = root.findall(f".//{{*}}{self._TEXT_REGION}[{{*}}TextLine]")
        self.text_region_list = [TextRegion(e, line_height=self.line_height) for e in tr]
        self.text_region_dict = {tr.text_region.get('id'): tr for tr in self.text_region_list}

        self.sort_text_region()

    def __repr__(self) -> str:
        return self.file

    def parse_reading_order(self, root) -> List[str]:
        reading_order_elements = root.findall(f".//{{*}}OrderedGroup//{{*}}RegionRefIndexed")
        reading_order = [el.get("regionRef") for el in reading_order_elements]
        return reading_order

    def sort_text_region(self) -> None:
        if not self.text_region_dict:
            return
        ordered_text_regions = [self.text_region_dict[region_id] for region_id in self.reading_order if region_id in self.text_region_dict]
        self.text_region_list = ordered_text_regions


class TextRegion:
    _COORDS = "Coords"
    _GLYPH = "Glyph"
    _ID = "id"
    _TEXT_LINE = "TextLine"
    _POINTS = "points"
    _WORD = "Word"

    def __init__(self, text_region: etree._Element, line_height: int = 50):
        if line_height < 0:
            raise ValueError("line_height need to be positive")
        self.text_region = text_region
        self.type = text_region.get("type")
        self.line_height = line_height
        self.line: List["TextLine"] = self.get_lines()
        self.x = self.line[0].x
        self.y = self.line[0].y

    def convert_coordinates(self, points: str) -> List[Tuple[int, int]]:
        result = []
        for p in points.split(' '):
            x, y = p.split(',')
            result.append((int(x), int(y)))
        return result

    def get_reference_point(self, points: List[Tuple[int, int]]) -> Tuple[int, int]:
        reference_point = sorted(points, key=itemgetter(1, 0))[0]
        return reference_point

    def get_lines(self) -> List["TextLine"]:
        text_line = self.text_region.findall(f".//{{*}}{self._TEXT_LINE}")
        lines = []

        if self.text_region.find(f".//{{*}}{self._GLYPH}") is None:
            for line in text_line:
                reference_point = self.convert_coordinates(line.find(f"./{{*}}{self._COORDS}").get(self._POINTS))
                reference_point = self.get_reference_point(reference_point)
                lines.append(TextLine(line, reference_point))
        else:
            for line in text_line:
                try:
                    reference_point = self.convert_coordinates(line.find(f".//{{*}}{self._GLYPH}/{{*}}{self._COORDS}").get(self._POINTS))
                    reference_point = self.get_reference_point(reference_point)
                    lines.append(TextLine(line, reference_point))
                except AttributeError:
                    pass
        lines.sort(key=attrgetter("y"))
        return lines

    def set_horizontal_group(self, horizontal_group: int):
        self.horizontal_group = horizontal_group

    def __str__(self):
        lines_text = "\n".join([str(line) for line in self.line])
        return f"type={self.type}\n{lines_text}\n])"

class TextLine:
    _INDEX = "index"
    _TEXT_EQUIV = "TextEquiv"
    _UNICODE = "Unicode"

    def __init__(self, text_line: etree._Element, reference_point: Tuple[int, int]):
        self.text_line = text_line
        self.x, self.y = reference_point

    def get_text(self) -> str:
        te = self.text_line.findall(f"./{{*}}{self._TEXT_EQUIV}[@{self._INDEX}]")
        text_equiv = [[e.get(self._INDEX), e.find(f"./{{*}}{self._UNICODE}").text] for e in te]
        text_equiv.sort(key=itemgetter(0))
        try:
            return text_equiv[0][1]
        except IndexError:
            return ""

    def __str__(self):
        text = self.get_text()
        return f"{text}\nTextLine(x={self.x}, y={self.y})"

class Conversion:
    _FRONT = "front"
    _BODY = "body"
    _SPLIT = " .,"

    def __init__(self, folder: str = None):
        if folder:
            self.file_list = glob.glob(folder)
            self.file_list.sort()
            self.file_iter = iter(self.file_list)
            self.current_file = next(self.file_iter, "end")
            self.page = Page(self.current_file)
            self._text_part = self._FRONT
        self.__previous_type = None
        self.__front = None
        self.__title_page = None
        self.__is_title_page_created = False
        self.__div_preface = None
        self.__prologue = None
        self.__act = None
        self.__scene = None
        self.__stage = None
        self.__cast_list = None
        self.__cast_item = None
        self.__sp_grp = None
        self.__sp = None
        self.__set = None

    def create_tei(self, file: str):
        WRONG = ""
        BODY_MARKER = ["header", "heading", "floating", "credit", "drop-capital"]

        root = etree.Element("TEI", attrib={"xmlns": "http://www.tei-c.org/ns/1.0", "{http://www.w3.org/XML/1998/namespace}id": "ger000", "{http://www.w3.org/XML/1998/namespace}lang": "de"})
        tree = etree.ElementTree(root)
        pi1 = etree.ProcessingInstruction("xml-stylesheet", 'type="text/css" href="../css/tei.css"')
        pi2 = etree.ProcessingInstruction("xml-model", 'href="https://dracor.org/schema.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"')
        tree.getroot().addprevious(pi1)
        tree.getroot().addprevious(pi2)

        f = BytesIO()
        act_number = 0
        try:
            with etree.xmlfile(f, encoding="utf-8") as xf:
                xf.write(pi1)
                xf.write(pi2)
                with xf.element("TEI", xmlns="http://www.tei-c.org/ns/1.0", attrib={"xml:id": "ger000", "xml:lang": "de"}):
                    with xf.element("teiHeader"):
                        with xf.element("fileDesc"):
                            with xf.element("titleStmt"):
                                with xf.element("title"):
                                    xf.write(WRONG)
                            with xf.element("publicationStmt"):
                                with xf.element("publisher"):
                                    xf.write(WRONG)
                            with xf.element("sourceDesc"):
                                with xf.element("p"):
                                    xf.write(WRONG)

                    with xf.element("text"):
                        if self.page.text_region_list[0].type in BODY_MARKER:
                            self._text_part = self._BODY
                        if self._text_part == self._FRONT:
                            self.__front = etree.Element("front")
                            while self._text_part == self._FRONT:
                                for text_region in self.page.text_region_list:
                                    if text_region.type in BODY_MARKER:
                                        self.write_front(xf)
                                        break
                                    try:
                                        self.build_front(text_region)
                                    except Exception as e:
                                        print(f"{self.current_file} <--- FEHLER bei der Verarbeitung:\n{text_region}: {e}\n------------------------------\n")
                                if text_region is self.page.text_region_list[-1]:
                                    self.current_file = next(self.file_iter, "end")
                                    if self.current_file != "end":
                                        self.page = Page(self.current_file)
                                if self.page.text_region_list[0].type in BODY_MARKER:
                                    self.write_front(xf)
                                    break

                        if self._text_part == self._BODY:
                            with xf.element("body"):
                                while self.current_file != "end":
                                    for text_region in self.page.text_region_list:
                                        try:
                                            act_number = self.build_body(xf, text_region, act_number)
                                        except Exception as e:
                                            print(f"{self.current_file} <--- FEHLER bei der Verarbeitung\n{text_region}: {e}\n------------------------------\n")
                                    if text_region is self.page.text_region_list[-1]:
                                        self.current_file = next(self.file_iter, "end")
                                        if self.current_file != "end":
                                            self.page = Page(self.current_file)

            result = f.getvalue().decode("utf-8")
            with open(file, "w", encoding="utf-8") as f:
                prolog = """<?xml version="1.0" encoding="utf-8"?>
                            <?xml-stylesheet type="text/css" href="../css/tei.css"?>
                            <?xml-model href="https://dracor.org/schema.rng" type="application/xml" schematypens="http://relaxng.org/ns/structure/1.0"?>"""
                result = prolog + result
                f.write(result)
            print(f"{Path(file).name} bearbeitet")
        except Exception as e:
            print(f"{self.current_file} <--- FEHLER bei der Verarbeitung von:\n{e}\n------------------------------\n")

    def build_front(self, text_region: "TextRegion") -> None:
        UNKNOWN = "WARNING!, the following paragraph couldn't be handled\ncorrectly. You have to solve this by yourself."

        if self.__previous_type == "catch-word" and text_region.type != "catch-word":
            self.__is_title_page_created = True

        if text_region.type == "catch-word":
            if self.__is_title_page_created:
                self.__div_preface = etree.SubElement(self.__front, "div", type="preface")
                p = etree.SubElement(self.__div_preface, "p")
                p.text = "WARNING!, the following 'head' might be slightly misplaced. Maybe\nthere is a more suitable parent tag or it might be another title page."
                head = etree.SubElement(self.__div_preface, "head")
                head.text = self.concatenate_lines(text_region)
            else:
                if self.__previous_type != "catch-word":
                    self.__title_page = etree.SubElement(self.__front, "titlePage")
                    title_part = etree.SubElement(self.__title_page, "titlePart")
                    title_part.text = "WARNING!, it's just assumed that this is the title page, check\nthis. Also check if the following 'head' elements in 'front' may be (another)\ntitle page."
                title_part = etree.SubElement(self.__title_page, "titlePart")
                title_part.text = self.concatenate_lines(text_region)

        elif text_region.type == "other":
            if self.__previous_type not in ["other", "catch-word"] or self.__div_preface is None:
                self.__div_preface = etree.SubElement(self.__front, "div", type="preface")
            p = etree.SubElement(self.__div_preface, "p")
            p.text = self.concatenate_lines(text_region)

        elif text_region.type == "TOC-entry":
            if not (self.__previous_type == "TOC-entry" or self.__previous_type == "signature-mark") or self.__cast_list is None:
                self.__cast_list = etree.SubElement(self.__front, "castList")
            self.__cast_item = etree.SubElement(self.__cast_list, "castItem")
            role = etree.SubElement(self.__cast_item, "role")
            role.text = self.concatenate_lines(text_region)

        elif text_region.type == "signature-mark":
            if self.__cast_item is None:
                cast_list_replace = etree.SubElement(self.__front, "castList")
                cast_item_replace = etree.SubElement(cast_list_replace, "castItem")
                role = etree.SubElement(cast_item_replace, "role")
                role.text = "WARNING!, it seems that the role is missing. You should fix this."
                role_desc = etree.SubElement(cast_item_replace, "roleDesc")
            else:
                role_desc = etree.SubElement(self.__cast_item, "roleDesc")
            role_desc.text = self.concatenate_lines(text_region)
        elif text_region.type == "footnote":
            user_note = etree.SubElement(self.__front, "div", type="notes")
            p = etree.SubElement(user_note, "p")
            p.text = "WARNING!, this footnote couldn't be placed correctly, you have to\nsolve this by yourself."
            footnote = etree.SubElement(user_note, "note", place="foot")
            footnote.text = self.concatenate_lines(text_region)
        else:
            unknown = etree.SubElement(self.__front, "div", type="notes")
            type_ = "type = " + text_region.type
            content = self.concatenate_lines(text_region)
            p_list = [UNKNOWN, type_, content]
            for e in p_list:
                p = etree.SubElement(unknown, "p")
                p.text = e

        self.__previous_type = text_region.type

    def write_front(self, xf: "etree._IncrementalFileWriter"):
        set_ = etree.SubElement(self.__front, "set")
        p = etree.SubElement(set_, "p")
        p.text = "WARNING!, the description of the setting (if existing) may\nbe misplaced as a 'roleDesc' element in the 'castList'. Place it at the correct place in an element like this."
        xf.write(self.__front)
        self._text_part = self._BODY

    def build_body(self, xf: "etree._IncrementalFileWriter", text_region: "TextRegion", act_number: int) -> int:
        UNKNOWN = "WARNING!, the following paragraph couldn't be handled\ncorrectly. You have to solve this by yourself."

        if text_region.type == "header":
            if etree.iselement(self.__prologue):
                xf.write(self.__prologue)
                self.__prologue = None
            act_number += 1
            if act_number > 1:
                xf.write(self.__act)
            self.__act = etree.Element("div", type="act")
            head = etree.SubElement(self.__act, "head")
            head.text = self.concatenate_lines(text_region)

        elif text_region.type == "heading":
            if self.__act is None:
                if etree.iselement(self.__prologue):
                    xf.write(self.__prologue)
                self.__prologue = etree.Element("div", type="prologue")
                head = etree.SubElement(self.__prologue, "head")
                head.text = self.concatenate_lines(text_region)
            else:
                self.__scene = etree.SubElement(self.__act, "div", type="scene")
                head = etree.SubElement(self.__scene, "head")
                head.text = self.concatenate_lines(text_region)
                stage = etree.SubElement(self.__scene, "stage")
                self.__cast_list = etree.SubElement(stage, "castList")
            print("Initialized scene:", self.__scene)  # Debugging-Statement

        elif text_region.type == "TOC-entry":
            cast_item = etree.SubElement(self.__cast_list, "castItem")
            cast_item.text = self.concatenate_lines(text_region)

        elif text_region.type == "signature-mark":
            if etree.iselement(self.__prologue):
                stage = etree.SubElement(self.__prologue, "stage")
            else:
                stage = etree.SubElement(self.__scene, "stage")
            stage.text = self.concatenate_lines(text_region)

        elif text_region.type == "floating":
            if etree.iselement(self.__prologue):
                self.__sp_grp = etree.SubElement(self.__prologue, "spGrp")
            else:
                self.__sp_grp = etree.SubElement(self.__scene, "spGrp")
            head = etree.SubElement(self.__sp_grp, "head")
            head.text = self.concatenate_lines(text_region)
            sp = etree.SubElement(self.__sp_grp, "sp")
            speaker = etree.SubElement(sp, "speaker")
            speaker.text = "WARNING!"
            p = etree.SubElement(sp, "p")
            p.text = "WARNING! Place the closing 'spGrp' tag after the last 'sp' tag of the\nsinging."

        elif text_region.type in ["credit", "drop-capital"]:
            if etree.iselement(self.__prologue):
                self.__sp = etree.SubElement(self.__prologue, "sp")
            else:
                if self.__scene is None:
                    # Falls die Szene nicht initialisiert wurde
                    print("Error: Scene not initialized")
                    self.__scene = etree.SubElement(self.__act, "div", type="scene")
                    print("Initialized scene in fallback")
                self.__sp = etree.SubElement(self.__scene, "sp")
            speaker = etree.SubElement(self.__sp, "speaker")
            speaker.text = self.concatenate_lines(text_region)

        elif text_region.type == "paragraph":
            if self.__sp is None:
                self.__sp = etree.SubElement(self.__scene, "sp")
                speaker = etree.SubElement(self.__sp, "speaker")
                speaker.text = "WARNING!, it seems that the speaker is missing."
            p = etree.SubElement(self.__sp, "p")
            p.text = self.concatenate_lines(text_region)

        elif text_region.type == "caption":
            if self.__previous_type == "header":
                # Start collecting captions in a div with type="set"
                if self.__set is None:
                    self.__set = etree.SubElement(self.__act, "div", type="set")
                p = etree.SubElement(self.__set, "p")
                p.text = self.concatenate_lines(text_region)
                self.__current_scenario = "set"

            elif self.__previous_type == "caption" and self.__current_scenario == "set":
                # Continue adding captions to the same set
                p = etree.SubElement(self.__set, "p")
                p.text = self.concatenate_lines(text_region)

            elif self.__previous_type == "paragraph":
                self.__stage = etree.SubElement(self.__scene, "stage")
                # Start a new scenario
                p = etree.SubElement(self.__stage, "p")
                p.text = self.concatenate_lines(text_region)
                self.__current_scenario = "paragraph"

            elif self.__previous_type == "caption" and self.__current_scenario == "paragraph":
                # Continue adding captions to the same set
                p = etree.SubElement(self.__stage, "p")
                p.text = self.concatenate_lines(text_region)

            else:
                # Process caption normally
                if self.__previous_type in ["credit", "heading", "scene"]:
                    if self.__sp is not None:
                        stage = etree.SubElement(self.__sp, "stage")
                    else:
                        stage = etree.SubElement(self.__scene, "stage")
                    stage.text = self.concatenate_lines(text_region)
                    self.__current_scenario = "normal"

                else:
                    if etree.iselement(self.__prologue):
                        stage = etree.SubElement(self.__prologue, "stage")
                    else:
                        stage = etree.SubElement(self.__scene, "stage")
                    stage.text = self.concatenate_lines(text_region)
                    self.__current_scenario = "normal"

        elif text_region.type == "footnote":
            if etree.iselement(self.__prologue):
                user_note = etree.SubElement(self.__prologue, "div", type="notes")
            else:
                user_note = etree.SubElement(self.__scene, "div", type="notes")
            p = etree.SubElement(user_note, "p")
            p.text = "WARNING!, this footnote couldn't be placed correctly, you have to\nsolve this by yourself. Source file: " + self.current_file.split("/")[-1]
            footnote = etree.SubElement(user_note, "note", place="foot")
            footnote.text = self.concatenate_lines(text_region)

        elif text_region.type == "catch-word":
            if self.__scene is None:
                p = etree.Element("p")
                p.text = "WARNING!, the following 'head' element might be misplaced, i.e.\nthere could be a better place."
                caption = etree.Element("head")
                caption.text = self.concatenate_lines(text_region)
                xf.write(p)
                xf.write(caption)
            else:
                caption = etree.SubElement(self.__scene, "div", type="notes")
                message = "WARNING!, the element isn't placed correctly, it still needs a solution."
                type_ = "type = " + text_region.type
                content = self.concatenate_lines(text_region)
                p_text = [message, type_, content]
                for text in p_text:
                    p = etree.SubElement(caption, "p")
                    p.text = text

        else:
            if etree.iselement(self.__prologue):
                unknown = etree.SubElement(self.__scene, "div", type="notes")
            else:
                unknown = etree.SubElement(self.__scene, "div", type="notes")
            type_ = "type = " + text_region.type
            content = self.concatenate_lines(text_region)
            p_list = [UNKNOWN, type_, content]
            for e in p_list:
                p = etree.SubElement(unknown, "p")
                p.text = e
        if self.current_file is self.file_list[-1] and text_region is self.page.text_region_list[-1]:
            xf.write(self.__act)
        self.__previous_type = text_region.type

        return act_number

    def concatenate_lines(self, text_region: "TextRegion") -> str:
        text = [ln.get_text() for ln in text_region.line]
        return "\n".join(filter(None, text))
    

if __name__ == '__main__':
    folder = Path('data')  # Pfad zum Ordner mit Page-XMLs
    result_file = 'output/Datei.xml'  # Pfad zur Ausgabedatei
    Conversion(str(folder / "*.xml")).create_tei(result_file)