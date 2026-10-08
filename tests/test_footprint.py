"""Parcel-table parsing on synthetic notices that copy the four layouts seen in the BOE."""
from dataclasses import asdict

from observatorio import footprint as fp


def _doc(body: str) -> bytes:
    return f"<documento><texto>{body}</texto></documento>".encode()


def test_polygon_parcel_with_municipality_rows():
    # Ministry of Agriculture style: «T.M.» rows inside the table, areas in m².
    xml = _doc("""<table>
      <tr><th>EXPTE</th><th>POL</th><th>PAR</th><th>TITULARES</th><th>EXP (m2)</th><th>SER LE (m2)</th><th>OT (m2)</th></tr>
      <tr><td>T.M. ARNEDO (LA RIOJA)</td></tr>
      <tr><td>01001</td><td>8</td><td>144</td><td>PEREZ PEREZ JUAN</td><td>2</td><td>0</td><td>1.054</td></tr>
    </table>""")
    [p] = fp.parse_tables(xml)
    assert (p.municipality, p.polygon, p.parcel) == ("ARNEDO (LA RIOJA)", 8, 144)
    assert p.expropriation_m2 == 2 and p.temporary_m2 == 1054


def test_full_cadastral_reference():
    xml = _doc("""<table>
      <tr><td>TERMINO MUNICIPAL DE NAVA</td></tr>
      <tr><th>N.º Finca</th><th>Ref. Catastral</th><th>Expropiación (m²)</th><th>Ocupación Temporal (m²)</th><th>Propietarios</th><th>DNI/NIF</th></tr>
      <tr><td>0002</td><td>33040A107000610000GO</td><td>0</td><td>152</td><td>GOMEZ GOMEZ ANA</td><td>***1234**</td></tr>
    </table>""")
    [p] = fp.parse_tables(xml)
    assert p.refcat == "33040A10700061" and p.office_code == "33040"
    assert (p.polygon, p.parcel) == (107, 61)


def test_municipality_in_paragraph_before_table():
    # ADIF style: the municipality is a paragraph, not a table row.
    xml = _doc("""<p>Término Municipal de Puertollano</p>
      <table><tr><th>Nº de Finca</th><th>Polígono/Ref Catastral</th><th>Parcela</th><th>Titular Actual</th></tr>
      <tr><td>Y-1</td><td>6</td><td>800</td><td>X</td></tr></table>
      <p>Término Municipal de Guadalmez</p>
      <table><tr><th>Nº de Finca</th><th>Polígono/Ref Catastral</th><th>Parcela</th><th>Titular Actual</th></tr>
      <tr><td>Y-2</td><td>3</td><td>12</td><td>X</td></tr></table>""")
    a, b = fp.parse_tables(xml)
    assert (a.municipality, a.polygon, a.parcel) == ("Puertollano", 6, 800)
    assert (b.municipality, b.polygon, b.parcel) == ("Guadalmez", 3, 12)


def test_banner_row_and_linear_metres():
    # Enagás style: municipality inside a banner row; «SP (ML)» is metres of pipe, not an area.
    xml = _doc("""<table>
      <tr><td>RELACION CONCRETA E INDIVIDUALIZADA PROVINCIA: T-TARRAGONA MUNICIPIO: CA-CAMBRILS ABREVIATURAS UTILIZADAS: SP-SERVIDUMBRE</td></tr>
      <tr><th>FINCA N.</th><th>TITULAR</th><th>SP (ML)</th><th>OT (M2)</th><th>POL</th><th>PAR</th><th>RC</th></tr>
      <tr><td>T-CA-1</td><td>X</td><td>120</td><td>900</td><td>23</td><td>8</td><td>43037A02300008</td></tr>
    </table>""")
    [p] = fp.parse_tables(xml)
    assert p.municipality == "CAMBRILS"
    assert p.refcat == "43037A02300008"
    assert p.easement_m2 == 0 and p.temporary_m2 == 900


def test_owner_columns_never_kept():
    xml = _doc("""<table><tr><th>POL</th><th>PAR</th><th>TITULAR</th><th>DNI</th></tr>
      <tr><td>1</td><td>2</td><td>NOMBRE SECRETO</td><td>12345678Z</td></tr></table>""")
    [p] = fp.parse_tables(xml, "Nava")
    assert "SECRETO" not in str(asdict(p)) and "12345678Z" not in str(asdict(p))


def test_municipality_keys():
    assert fp._muni_key("Los Corrales de Buelna") == fp._muni_key("CORRALES DE BUELNA (LOS)")
    assert fp._muni_key("Vandellòs i l'Hospitalet de l'Infant") == fp._muni_key("VANDELLOS I L'HOSPITALET DE L'INFANT")


def test_detection():
    assert fp.lists_affected_land("Relación concreta e individualizada de bienes y derechos afectados")
    assert not fp.lists_affected_land("Información pública del estudio de impacto ambiental")
