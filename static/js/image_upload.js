  const form = document.querySelector("form");
  const fileInput = document.getElementById("profile_image");
  const hiddenInput = document.getElementById("profile_image_url");
  const loginBtn = document.getElementById("loginBtn");

  async function compressImage(file) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();

      reader.onload = function (e) {
        img.src = e.target.result;
      };

      img.onload = function () {
        const canvas = document.createElement("canvas");
        const maxSize = 900;

        let width = img.width;
        let height = img.height;

        if (width > height && width > maxSize) {
          height = height * (maxSize / width);
          width = maxSize;
        } else if (height > maxSize) {
          width = width * (maxSize / height);
          height = maxSize;
        }

        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          function (blob) {
            resolve(new File([blob], "profile-image.jpg", {
              type: "image/jpeg"
            }));
          },
          "image/jpeg",
          0.75
        );
      };

      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    loginBtn.disabled = true;
    loginBtn.textContent = "Saving...";

    const file = fileInput.files[0];

    try {
      if (file) {
        const compressedFile = await compressImage(file);

        const response = await fetch("/api/upload", {
          method: "POST",
          headers: {
            "x-vercel-filename": compressedFile.name,
          },
          body: compressedFile,
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Upload failed: ${response.status} - ${errorText}`);
        }

        const blob = await response.json();
        hiddenInput.value = blob.url;
      }

      form.submit();

    } catch (error) {
      console.error(error);
      alert(error.message);

      loginBtn.disabled = false;
      loginBtn.textContent = "Save Profile";
    }
  });