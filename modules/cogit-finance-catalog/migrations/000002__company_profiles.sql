-- Public company descriptions and prospective-buyer programme information.
ALTER TABLE cat_companies ADD COLUMN profile TEXT NOT NULL DEFAULT '{}';
