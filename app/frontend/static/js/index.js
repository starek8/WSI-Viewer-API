const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");

dropzone.addEventListener("click", () => fileInput.click());

dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) {
        await uploadFile(file);
    }
});

fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) {
        await uploadFile(file);
    }
});

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch("/upload", {
        method: "POST",
        body: formData,
    });

    if (res.redirected) {
        window.location.href = res.url;
    } else {
        alert("Upload failed: " + (await res.text()));
    }
}
