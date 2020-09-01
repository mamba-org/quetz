<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
        <h3 class="bx--data-table-header">Users</h3>
        <cv-data-table
          :columns="columns" :data="data" ref="table">
          <template slot="data">
            <cv-data-table-row v-for="(row, rowIndex) in data" :key="`${rowIndex}`" :value="`${rowIndex}`">
               <cv-data-table-cell>{{ row[0] }}</cv-data-table-cell>
               <cv-data-table-cell>{{ row[1] }}</cv-data-table-cell>
               <cv-data-table-cell>
                <img :src=row[2] class="avatar" />
              </cv-data-table-cell>
            </cv-data-table-row>
          </template>
        </cv-data-table>
    </div>
  </div>
</div>
</template>


<script>
  export default {
    data: function () {
      return {
        columns: [],
        data: [],
        loading: true
      }
    },
    methods: {
      fetchData: function() {
        return fetch("/api/users").then((msg) => {
          console.log(msg);
          return msg.json().then((decoded) => {
              this.columns = ["Username", "Name", "Avatar URL"];
              this.data = decoded.map((el) => [el.username, el.profile.name, el.profile.avatar_url]);
          });
        });
      }
    },
    created: function() {
      this.fetchData();
    },
}
</script>

<style>
.avatar
{
  height: 30px;
  width: 30px;
  border-radius: 5px;
}
</style>
