import io

import pytest

from backend.src.sessions import files as files_service


def test_save_uploaded_file_writes_to_uploads_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(files_service, "UPLOADS_DIR", tmp_path)

    data = io.BytesIO(b"alpha,beta\n1,2\n")
    saved = files_service.save_uploaded_file("example.csv", data)

    assert saved.name == "example.csv"
    assert (tmp_path / "example.csv").is_file()


def test_delete_one_upload_removes_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(files_service, "UPLOADS_DIR", tmp_path)

    target = tmp_path / "remove.csv"
    target.write_text("a,b\n1,2\n")

    deleted = files_service.delete_one_upload("remove.csv")

    assert deleted == "remove.csv"
    assert not target.exists()


def test_delete_one_upload_rejects_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(files_service, "UPLOADS_DIR", tmp_path)

    with pytest.raises(files_service.UploadNameError):
        files_service.delete_one_upload("../evil.csv")


def test_excel_file_upload_and_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(files_service, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(files_service, "_DATA_ROOT", tmp_path)

    import pandas as pd

    df = pd.DataFrame({"col_a": [10, 20], "col_b": ["x", "y"]})
    
    excel_io = io.BytesIO()
    df.to_excel(excel_io, index=False)
    excel_io.seek(0)
    
    saved = files_service.save_uploaded_file("test.xlsx", excel_io)
    assert saved.name == "test.xlsx"
    assert (tmp_path / "test.xlsx").is_file()

    preview = files_service.read_file_preview(
        tmp_path / "test.xlsx",
        sample_rows=2,
        include_total=True
    )
    assert preview.table == "test"
    assert preview.columns == ["col_a", "col_b"]
    assert preview.total_rows == 2
    assert preview.rows == [["10", "x"], ["20", "y"]]

