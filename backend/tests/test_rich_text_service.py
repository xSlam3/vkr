from app.services.rich_text_service import RichTextService


def test_sanitize_preserves_table_markup():
    html = """
    <table>
      <caption>Physical properties</caption>
      <thead>
        <tr>
          <th scope="col">Metal</th>
          <th scope="col">Density</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Gold</td>
          <td>19320</td>
        </tr>
      </tbody>
    </table>
    """

    cleaned = RichTextService.sanitize(html)

    assert "<table>" in cleaned
    assert "<caption>Physical properties</caption>" in cleaned
    assert '<th scope="col">Metal</th>' in cleaned
    assert "<td>19320</td>" in cleaned


def test_sanitize_strips_unsafe_table_content():
    html = """
    <table onclick="alert(1)">
      <tbody>
        <tr>
          <td colspan="2" onclick="alert(1)">Safe</td>
        </tr>
      </tbody>
    </table>
    <script>alert(1)</script>
    """

    cleaned = RichTextService.sanitize(html)

    assert "onclick" not in cleaned
    assert "<script>" not in cleaned
    assert '<td colspan="2">Safe</td>' in cleaned
