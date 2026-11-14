package repository

import (
	"encoding/json"
	"log"
	"os"
	"strings"

	"hakathon/models"

	"github.com/glebarez/sqlite"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
)

var db *gorm.DB

func Initdb() {
	var err error
	db, err = gorm.Open(sqlite.Open("database.db"), &gorm.Config{})
	if err != nil {
		log.Println("Ошибка подключения к БД:", err)
	}

	// Сносим таблицу заданий, чтобы подтягивать свежий датасет
	db.Migrator().DropTable(&models.Task{})
	db.AutoMigrate(&models.Auth{}, &models.User{}, &models.Task{})

	// КРИТИЧЕСКИ ВАЖНО: эта строчка запускает парсер!
	loadDatasetFromFile("dataset.json")
}

func loadDatasetFromFile(filename string) {
	fileBytes, err := os.ReadFile(filename)
	if err != nil {
		log.Println("⚠️ Файл датасета не найден. Убедись, что он называется dataset.json!")
		return
	}

	// Разбиваем весь файл на отдельные строки
	lines := strings.Split(string(fileBytes), "\n")
	var tasks []models.Task

	for _, line := range lines {
		// 1. Убираем пробелы по краям
		line = strings.TrimSpace(line)

		// 2. Пропускаем пустые строки или открывающие/закрывающие скобки массива
		if line == "" || line == "[" || line == "]" {
			continue
		}

		// 3. САМОЕ ГЛАВНОЕ: Убиваем ту самую запятую в конце строки!
		line = strings.TrimSuffix(line, ",")

		// Теперь это чистый JSON-объект, парсим его
		var item map[string]interface{}
		if err := json.Unmarshal([]byte(line), &item); err == nil {
			textBa, okBa := item["text_ba"].(string)
			textRu, okRu := item["text_ru"].(string)

			if okBa && okRu {
				tasks = append(tasks, models.Task{
					TextBa:      textBa,
					Translation: textRu,
					CorrectHint: textRu,
				})
			}
		}
	}

	if len(tasks) > 0 {
		db.CreateInBatches(tasks, 100)
		log.Printf("✅ БАЗА ЗАРЯЖЕНА! Успешно загружено %d башкирских фраз из датасета!\n", len(tasks))
	} else {
		log.Println("⚠️ ВНИМАНИЕ: Фразы не загрузились! Ни одна строка не распарсилась.")
	}
}

func FindAuthByEmail(email string) (*models.Auth, error) {
	var auth models.Auth
	err := db.Where("email = ?", email).First(&auth).Error
	return &auth, err
}

func ReadAuth(id uint) (*models.Auth, error) {
	var auth models.Auth
	err := db.First(&auth, id).Error
	return &auth, err
}

func CreateUser(req *models.RequestRegister) (uint, error) {
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return 0, err
	}

	auth := models.Auth{Email: req.Email, Password: string(hashedPassword), Role: "student"}
	tx := db.Begin()
	if err := tx.Create(&auth).Error; err != nil {
		tx.Rollback()
		return 0, err
	}

	user := models.User{AuthID: auth.ID, Name: req.Name, Surname: req.Surname}
	if err := tx.Create(&user).Error; err != nil {
		tx.Rollback()
		return 0, err
	}

	tx.Commit()
	return auth.ID, nil
}

func GetRandomTask() (models.Task, error) {
	var task models.Task
	err := db.Order("RANDOM()").First(&task).Error
	return task, err
}

func GetTaskByID(id uint) (models.Task, error) {
	var task models.Task
	err := db.First(&task, id).Error
	return task, err
}

// --- ФУНКЦИИ ГЕЙМИФИКАЦИИ ---

// 1. Получить профиль пользователя по его AuthID
func GetUserByAuthID(authID uint) (*models.User, error) {
	var user models.User
	if err := db.Where("auth_id = ?", authID).First(&user).Error; err != nil {
		return nil, err
	}
	return &user, nil
}

// 2. Сохранить обновленный опыт и списки слов
func UpdateUserStats(user *models.User) error {
	return db.Save(user).Error
}

// Структура для красивого вывода рейтинга
type RatingEntry struct {
	Name  string `json:"name"`
	Score int    `json:"score"`
}

// 3. Получить Топ-10 пользователей для турнирной таблицы
func GetTopUsers() ([]RatingEntry, error) {
	var users []models.User
	var rating []RatingEntry

	// Сортируем по убыванию очков, берем максимум 10 человек
	if err := db.Order("score desc").Limit(10).Find(&users).Error; err != nil {
		return nil, err
	}

	for _, u := range users {
		if u.Score > 0 { // В рейтинг попадают только те, кто начал учиться
			rating = append(rating, RatingEntry{Name: u.Name, Score: u.Score})
		}
	}
	return rating, nil
}
