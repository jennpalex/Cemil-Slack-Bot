# Katkıda Bulunma Rehberi (Contributing Guide)

Cemil Bot projesine katkıda bulunmak istediğiniz için teşekkürler! 🎉

Bu proje açık kaynaklıdır ve topluluk katkılarıyla büyümeyi hedefler. İster bir hata düzeltmesi, ister yeni bir özellik, ister dokümantasyon iyileştirmesi olsun, her türlü katkı değerlidir.

## Nasıl Katkıda Bulunabilirim?

### 1. Hata Bildirimi (Bug Reporting)
Bir hata bulursanız, lütfen GitHub Issues üzerinden bildirin.
- Sorunu net bir başlık ile özetleyin.
- Hatayı tekrar etmek için gereken adımları listeleyin.
- Varsa log kayıtlarını veya ekran görüntülerini ekleyin.

### 2. Özellik İsteği (Feature Request)
Yeni bir fikir mi var? Issues bölümünde "Feature Request" etiketiyle bir tartışma başlatın.
- Bu özellik neyi çözecek?
- Nasıl çalışması gerektiğini düşünüyorsunuz?

### 3. Kod İle Katkı (Pull Request)

1. **Projeyi Fork'layın**
   - Sağ üstteki "Fork" butonuna tıklayarak kendi hesabınıza kopyalayın.

2. **Geliştirme Ortamını Kurun**
   ```bash
   git clone https://github.com/SİZİN_KULLANICI_ADINIZ/cemil-bot.git
   cd cemil-bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Yeni Bir Branch Açın**
   - Branch isimleri açıklayıcı olmalıdır: `feat/kahve-tarihcesi`, `fix/oylama-bug` gibi.
   ```bash
   git checkout -b feat/yeni-ozellik
   ```

4. **Değişikliklerinizi Yapın**
   - Kod standartlarına uyun (PEP 8).
   - Mümkünse mevcut testleri çalıştırın veya yeni test ekleyin.

5. **Commit Atın**
   - Commit mesajlarınızda [Conventional Commits](https://www.conventionalcommits.org/) formatını kullanmaya özen gösterin:
     - `feat: ...` (Yeni özellik)
     - `fix: ...` (Hata düzeltmesi)
     - `docs: ...` (Dokümantasyon)
     - `style: ...` (Formatlama, noktalama vb.)
     - `refactor: ...` (Kod iyileştirme)

6. **Pull Request (PR) Gönderin**
   - GitHub üzerinde Fork'unuzdan ana projeye PR açın.
   - PR açıklamasında yaptığınız değişiklikleri özetleyin.

## Geliştirme Kuralları

- **Python Versiyonu:** Proje Python 3.10+ ile uyumludur.
- **Kod Stili:** Okunabilir ve modüler kod yazmaya özen gösterin. Black veya autopep8 kullanabilirsiniz.
- **Tip İpuçları:** Mümkün olduğunca Type Hinting (`typing` modülü) kullanın.
- **Loglama:** `print` yerine `src.core.logger` kullanın.

## İletişim

Sorularınız için GitHub Issues bölümünü kullanabilirsiniz.

---
Katkılarınızla Cemil'i daha da akıllı hale getirdiğiniz için teşekkürler! 🚀
